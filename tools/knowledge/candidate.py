"""Authoring CLI for multi-candidate proofs (issue #159).

Operations:

- ``spawn``    create a new proof attempt for a canonical theorem,
               migrating a single-file canonical to the dir layout on first
               use.
- ``promote``  make a verified candidate the active proof; retire the
               previously-promoted sibling.
- ``abandon``  retire a non-promoted candidate, preserving any helpers it
               introduced.
- ``list``     report the candidates of a canonical.

Edge ownership (locked 2026-05-28): a multi-candidate canonical carries
``uses: []`` and the **promoted candidate is the sole edge source**. Spawn
moves a migrated node's dependencies onto ``cand_a``; ``promote`` only flips
statuses and the ``promoted_candidate`` pointer. This keeps exactly one edge
owner at all times and avoids double-counted dependency edges.

Concurrency: this CLI does not lock files. Parallel ``spawn`` operations
against the *same* canonical id are racy and should be serialised by the
calling workflow. Every operation validates the post-write state and rolls
back on failure, so a lost race fails loudly rather than corrupting the tree.
"""
from __future__ import annotations

import argparse
import json
import string
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.admit import admission_evidence_diagnostics
from tools.knowledge.candidate_layout import (
    canonical_proof_source,
    discover_canonical_groups,
    proof_block_start,
)
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import parse_file, scan_directory
from tools.knowledge.validator import Diagnostic, validate_node
from tools.knowledge.candidate_layout import validate_canonical_groups

import re

_SLUG_RE = re.compile(r"^[a-z0-9_]{1,16}$")


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SpawnResult:
    success: bool
    canonical_id: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    new_slug: str | None = None
    migrated: bool = False
    canonical_path: Path | None = None
    candidate_path: Path | None = None


@dataclass
class PromoteResult:
    success: bool
    candidate_id: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    previous_slug: str | None = None
    review_path: Path | None = None


@dataclass
class AbandonResult:
    success: bool
    candidate_id: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    review_path: Path | None = None


@dataclass
class CandidateInfo:
    slug: str
    status: str
    is_promoted: bool
    file_path: Path
    abandoned_reason: str | None = None


# ── Frontmatter IO ──────────────────────────────────────────────────────────────

def _split_file(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ValueError("node file has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("node file has malformed YAML frontmatter")
    fm = yaml.safe_load(text[4:end]) or {}
    if not isinstance(fm, dict):
        raise ValueError("node frontmatter is not a mapping")
    return fm, text[end + len("\n---\n"):]


def _render(fm: dict[str, Any], body: str) -> str:
    rendered = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{rendered}\n---\n{body}"


def _err(node_id: str, message: str, path: Path | None = None) -> Diagnostic:
    return Diagnostic("error", node_id, message, path)


# ── Snapshot / rollback ──────────────────────────────────────────────────────────

def _snapshot(paths: list[Path]) -> list[tuple[Path, bytes | None]]:
    snap: list[tuple[Path, bytes | None]] = []
    for p in paths:
        snap.append((p, p.read_bytes() if p.exists() else None))
    return snap


def _rollback(snap: list[tuple[Path, bytes | None]]) -> None:
    for path, original in snap:
        if original is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)


def _apply_writes(
    snap: list[tuple[Path, bytes | None]],
    writes: list[tuple[Path, str]],
    deletes: list[Path],
    knowledge_root: Path,
) -> list[Diagnostic]:
    """Apply writes+deletes, validate, and roll back on any error.

    Returns an empty list on success, or the blocking diagnostics (after
    rolling back) on failure.
    """
    try:
        for path, text in writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for path in deletes:
            if path.exists():
                path.unlink()
        errors = _validate_tree(knowledge_root)
        if errors:
            _rollback(snap)
            return errors
        return []
    except Exception:
        _rollback(snap)
        raise


def _validate_tree(knowledge_root: Path) -> list[Diagnostic]:
    nodes = scan_directory(knowledge_root / "nodes")
    by_id = {n.id: n for n in nodes}
    errors: list[Diagnostic] = []
    for node in nodes:
        errors.extend(d for d in validate_node(node, is_staged_dir=False) if d.level == "error")
    groups = discover_canonical_groups(nodes)
    errors.extend(d for d in validate_canonical_groups(groups, by_id) if d.level == "error")
    _, gdiags = build_graph(nodes)
    errors.extend(d for d in gdiags if d.level == "error")
    return errors


# ── Helpers ──────────────────────────────────────────────────────────────────

def _local_id(canonical_id: str) -> str:
    return canonical_id.split(".")[-1]


def _next_free_slug(existing: list[str]) -> str:
    taken = set(existing)
    for ch in string.ascii_lowercase:
        slug = f"cand_{ch}"
        if slug not in taken:
            return slug
    i = 1
    while True:
        slug = f"cand_{i}"
        if slug not in taken:
            return slug
        i += 1


def _statement_text(body: str) -> str:
    """Statement block (H1 + prose), proof removed, stripped."""
    idx = proof_block_start(body)
    segment = body if idx is None else body[:idx]
    return segment.strip()


def _candidate_frontmatter(
    canonical_id: str,
    slug: str,
    kind: str,
    title: str,
    status: str,
    uses: list[str],
    proof: str,
) -> dict[str, Any]:
    return {
        "id": f"{canonical_id}._{slug}",
        "title": f"{title} ({slug})",
        "kind": kind,
        "status": status,
        "candidate_of": canonical_id,
        "candidate_slug": slug,
        "uses": list(uses),
        "verification": {"statement": "accepted", "proof": proof},
    }


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _emit_review(
    kind: str,
    canonical_id: str,
    slug: str,
    knowledge_root: Path,
    body: str,
) -> Path:
    review_dir = knowledge_root / "reviews" / canonical_id
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"{kind}-{slug}-{_utc_stamp()}.md"
    path.write_text(body, encoding="utf-8")
    return path


# ── spawn ──────────────────────────────────────────────────────────────────────

def spawn_candidate(
    canonical_id: str,
    *,
    knowledge_root: Path,
    slug: str | None = None,
) -> SpawnResult:
    nodes_dir = knowledge_root / "nodes"
    all_nodes = scan_directory(nodes_dir) if nodes_dir.exists() else []
    by_id = {n.id: n for n in all_nodes}
    canonical = by_id.get(canonical_id)
    if canonical is None or canonical.file_path is None:
        return SpawnResult(
            False, canonical_id,
            [_err(canonical_id, f"canonical not found: {canonical_id!r}")],
        )

    if slug is not None and not _SLUG_RE.match(slug):
        return SpawnResult(
            False, canonical_id,
            [_err(canonical_id, f"invalid candidate slug {slug!r}; must match ^[a-z0-9_]{{1,16}}$")],
        )

    migrated = canonical.candidate_layout != "multi"
    local = _local_id(canonical_id)

    if migrated:
        orig_path = canonical.file_path
        cdir = orig_path.parent / local
        canonical_path = cdir / "canonical.md"
        orig_text = orig_path.read_text(encoding="utf-8")
        orig_fm, orig_body = _split_file(orig_text)
        statement_text = _statement_text(orig_body)
        orig_uses = list(orig_fm.get("uses") or [])
        orig_v = orig_fm.get("verification") or {}
        kind = orig_fm.get("kind", canonical.kind)
        title = orig_fm.get("title", canonical.title)

        # canonical.md: statement only, uses delegated to cand_a.
        canonical_fm: dict[str, Any] = {}
        for key, value in orig_fm.items():
            canonical_fm[key] = value
            if key == "status":
                canonical_fm["candidate_layout"] = "multi"
                canonical_fm["promoted_candidate"] = "cand_a"
                canonical_fm["candidates"] = ["cand_a"]
        canonical_fm["uses"] = []
        canonical_body = "\n" + statement_text + "\n"

        # cand_a.md: the migrated proof (promoted), owns the dependencies.
        cand_a_fm = _candidate_frontmatter(
            canonical_id, "cand_a", kind, title, "promoted", orig_uses,
            proof=orig_v.get("proof", "accepted"),
        )
        cand_a_body = "\n" + orig_body.strip() + "\n"
        cand_a_path = cdir / "candidates" / "cand_a.md"

        baseline_uses = orig_uses
        existing_slugs = ["cand_a"]
        pre_writes = [
            (canonical_path, _render(canonical_fm, canonical_body)),
            (cand_a_path, _render(cand_a_fm, cand_a_body)),
        ]
        deletes = [orig_path]
        snapshot_paths = [orig_path, canonical_path, cand_a_path]
        canonical_for_append = canonical_fm
        canonical_append_path = canonical_path
        canonical_append_body = canonical_body
    else:
        cdir = canonical.file_path.parent
        canonical_path = canonical.file_path
        statement_text = _statement_text(canonical.body)
        existing = [n for n in all_nodes if n.candidate_of == canonical_id]
        existing_slugs = [n.candidate_slug for n in existing if n.candidate_slug]
        groups = {g.canonical.id: g for g in discover_canonical_groups(all_nodes)}
        source = canonical_proof_source(canonical_id, by_id, groups)
        baseline_uses = list(source.uses) if source is not None else list(canonical.uses)
        kind = canonical.kind
        title = canonical.title
        canonical_text = canonical_path.read_text(encoding="utf-8")
        canonical_for_append, canonical_append_body = _split_file(canonical_text)
        canonical_append_path = canonical_path
        pre_writes = []
        deletes = []
        snapshot_paths = [canonical_path]

    # Determine the new slug (with collision retry for auto-assignment).
    if slug is not None:
        if slug in existing_slugs:
            return SpawnResult(
                False, canonical_id,
                [_err(canonical_id, f"candidate slug {slug!r} already exists")],
            )
        attempts = [slug]
    else:
        attempts = []
        taken = list(existing_slugs)
        for _ in range(3):
            attempts.append(_next_free_slug(taken))
            taken.append(attempts[-1])

    last_errors: list[Diagnostic] = []
    for new_slug in attempts:
        cand_new_path = cdir / "candidates" / f"{new_slug}.md"
        cand_new_fm = _candidate_frontmatter(
            canonical_id, new_slug, kind, title, "candidate", baseline_uses,
            proof="gap",
        )
        cand_new_body = "\n" + statement_text + "\n\n*Proof.* TODO\n"

        # Canonical's candidates list gains the new slug.
        appended_fm = dict(canonical_for_append)
        candidates_list = list(appended_fm.get("candidates") or [])
        if migrated:
            candidates_list = ["cand_a", new_slug]
        else:
            candidates_list.append(new_slug)
        appended_fm["candidates"] = sorted(set(candidates_list))

        writes = list(pre_writes)
        writes.append((canonical_append_path, _render(appended_fm, canonical_append_body)))
        writes.append((cand_new_path, _render(cand_new_fm, cand_new_body)))

        snap = _snapshot(snapshot_paths + [cand_new_path])
        errors = _apply_writes(snap, writes, deletes, knowledge_root)
        if not errors:
            return SpawnResult(
                True, canonical_id, [], new_slug=new_slug, migrated=migrated,
                canonical_path=canonical_append_path, candidate_path=cand_new_path,
            )
        last_errors = errors
        # Auto-slug retry only makes sense for duplicate-id style collisions.
        if slug is not None:
            break

    return SpawnResult(False, canonical_id, last_errors, migrated=migrated)


# ── promote ──────────────────────────────────────────────────────────────────────

def promote_candidate(candidate_path: Path, *, knowledge_root: Path) -> PromoteResult:
    node = parse_file(candidate_path)
    cid = node.candidate_of
    if cid is None:
        return PromoteResult(False, node.id, [_err(node.id, "not a candidate (no candidate_of)")])
    if node.status not in {"candidate", "promoted"}:
        return PromoteResult(
            False, node.id,
            [_err(node.id, f"cannot promote a candidate with status {node.status!r}")],
        )
    if node.verification is None or node.verification.proof != "accepted":
        return PromoteResult(
            False, node.id,
            [_err(node.id, "verification.proof must be accepted before promotion")],
        )
    evidence = [d for d in admission_evidence_diagnostics(node) if d.level == "error"]
    if evidence:
        return PromoteResult(False, node.id, evidence)

    all_nodes = scan_directory(knowledge_root / "nodes")
    by_id = {n.id: n for n in all_nodes}
    groups = {g.canonical.id: g for g in discover_canonical_groups(all_nodes)}
    group = groups.get(cid)
    if group is None or group.canonical.file_path is None:
        return PromoteResult(False, node.id, [_err(node.id, f"canonical group not found for {cid!r}")])

    pre_errors = [d for d in validate_canonical_groups(list(groups.values()), by_id) if d.level == "error"]
    if pre_errors:
        return PromoteResult(False, node.id, pre_errors)

    canonical = group.canonical
    previous = [
        c for c in group.candidates
        if c.status == "promoted" and c.candidate_slug != node.candidate_slug
    ]
    timestamp = datetime.now(timezone.utc).isoformat()

    writes: list[tuple[Path, str]] = []
    snapshot_paths: list[Path] = []

    for prev in previous:
        assert prev.file_path is not None
        prev_fm, prev_body = _split_file(prev.file_path.read_text(encoding="utf-8"))
        prev_fm["status"] = "abandoned"
        prev_fm["abandoned_reason"] = f"superseded by {node.candidate_slug} at {timestamp}"
        writes.append((prev.file_path, _render(prev_fm, prev_body)))
        snapshot_paths.append(prev.file_path)

    cand_fm, cand_body = _split_file(candidate_path.read_text(encoding="utf-8"))
    cand_fm["status"] = "promoted"
    writes.append((candidate_path, _render(cand_fm, cand_body)))
    snapshot_paths.append(candidate_path)

    can_fm, can_body = _split_file(canonical.file_path.read_text(encoding="utf-8"))
    can_fm["promoted_candidate"] = node.candidate_slug
    verification = dict(can_fm.get("verification") or {})
    verification["proof"] = "accepted"
    can_fm["verification"] = verification
    writes.append((canonical.file_path, _render(can_fm, can_body)))
    snapshot_paths.append(canonical.file_path)

    snap = _snapshot(snapshot_paths)
    errors = _apply_writes(snap, writes, [], knowledge_root)
    if errors:
        return PromoteResult(False, node.id, errors)

    previous_slug = previous[0].candidate_slug if previous else None
    review = _render_promotion_review(cid, node.candidate_slug, previous_slug, timestamp)
    review_path = _emit_review("promotion", cid, node.candidate_slug or "?", knowledge_root, review)
    return PromoteResult(True, node.id, [], previous_slug=previous_slug, review_path=review_path)


def _render_promotion_review(
    canonical_id: str,
    slug: str | None,
    previous_slug: str | None,
    timestamp: str,
) -> str:
    retired = f"- Retired: `{previous_slug}`\n" if previous_slug else "- Retired: (none)\n"
    return (
        f"# Promotion: {canonical_id}\n\n"
        f"- Promoted: `{slug}`\n"
        f"{retired}"
        f"- Timestamp: {timestamp}\n\n"
        f"The candidate `{slug}` was promoted to the active proof for "
        f"`{canonical_id}`.\n"
    )


# ── abandon ──────────────────────────────────────────────────────────────────────

def abandon_candidate(
    candidate_path: Path,
    *,
    knowledge_root: Path,
    reason: str,
) -> AbandonResult:
    node = parse_file(candidate_path)
    cid = node.candidate_of
    if cid is None:
        return AbandonResult(False, node.id, [_err(node.id, "not a candidate (no candidate_of)")])
    if node.status == "promoted":
        return AbandonResult(
            False, node.id,
            [_err(node.id, "cannot abandon the promoted candidate; promote another candidate first")],
        )

    fm, body = _split_file(candidate_path.read_text(encoding="utf-8"))
    fm["status"] = "abandoned"
    fm["abandoned_reason"] = reason
    snap = _snapshot([candidate_path])
    errors = _apply_writes(snap, [(candidate_path, _render(fm, body))], [], knowledge_root)
    if errors:
        return AbandonResult(False, node.id, errors)

    timestamp = datetime.now(timezone.utc).isoformat()
    review = (
        f"# Abandonment: {cid}\n\n"
        f"- Abandoned: `{node.candidate_slug}`\n"
        f"- Reason: {reason}\n"
        f"- Timestamp: {timestamp}\n"
    )
    review_path = _emit_review("abandon", cid, node.candidate_slug or "?", knowledge_root, review)
    return AbandonResult(True, node.id, [], review_path=review_path)


# ── list ──────────────────────────────────────────────────────────────────────

def list_candidates(canonical_id: str, *, knowledge_root: Path) -> list[CandidateInfo]:
    all_nodes = scan_directory(knowledge_root / "nodes")
    by_id = {n.id: n for n in all_nodes}
    canonical = by_id.get(canonical_id)
    promoted_slug = canonical.promoted_candidate if canonical else None
    infos: list[CandidateInfo] = []
    for node in all_nodes:
        if node.candidate_of != canonical_id or not node.candidate_slug:
            continue
        assert node.file_path is not None
        infos.append(CandidateInfo(
            slug=node.candidate_slug,
            status=node.status,
            is_promoted=(node.candidate_slug == promoted_slug),
            file_path=node.file_path,
            abandoned_reason=node.abandoned_reason,
        ))
    infos.sort(key=lambda i: i.slug)
    return infos


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_diags(diags: list[Diagnostic]) -> None:
    for d in diags:
        print(d, file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mdblueprint-candidate",
        description=(
            "Manage multiple proof candidates per canonical theorem. "
            "NOTE: parallel spawn against the same canonical is racy; "
            "serialise such calls in the calling workflow."
        ),
    )
    parser.add_argument(
        "--knowledge-root", type=Path, default=Path("docs/knowledge"),
        help="knowledge base root (default: docs/knowledge)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_spawn = sub.add_parser("spawn", help="create a new proof attempt")
    p_spawn.add_argument("canonical_id")
    p_spawn.add_argument("--slug", default=None, help="explicit candidate slug")

    p_promote = sub.add_parser("promote", help="promote a verified candidate")
    p_promote.add_argument("candidate_path", type=Path)

    p_abandon = sub.add_parser("abandon", help="retire a non-promoted candidate")
    p_abandon.add_argument("candidate_path", type=Path)
    p_abandon.add_argument("--reason", required=True)

    p_list = sub.add_parser("list", help="list candidates of a canonical")
    p_list.add_argument("canonical_id")
    p_list.add_argument("--json", action="store_true")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = args.knowledge_root

    if args.command == "spawn":
        result = spawn_candidate(args.canonical_id, knowledge_root=root, slug=args.slug)
        if result.success:
            verb = "migrated + spawned" if result.migrated else "spawned"
            print(f"{verb} {args.canonical_id} -> {result.new_slug} ({result.candidate_path})")
        else:
            _print_diags(result.diagnostics)
            sys.exit(1)
    elif args.command == "promote":
        result = promote_candidate(args.candidate_path, knowledge_root=root)
        if result.success:
            retired = f" (retired {result.previous_slug})" if result.previous_slug else ""
            print(f"promoted {result.candidate_id}{retired}; review at {result.review_path}")
        else:
            _print_diags(result.diagnostics)
            sys.exit(1)
    elif args.command == "abandon":
        result = abandon_candidate(args.candidate_path, knowledge_root=root, reason=args.reason)
        if result.success:
            print(f"abandoned {result.candidate_id}; review at {result.review_path}")
        else:
            _print_diags(result.diagnostics)
            sys.exit(1)
    elif args.command == "list":
        infos = list_candidates(args.canonical_id, knowledge_root=root)
        if args.json:
            print(json.dumps([
                {
                    "slug": i.slug, "status": i.status, "is_promoted": i.is_promoted,
                    "file_path": str(i.file_path), "abandoned_reason": i.abandoned_reason,
                }
                for i in infos
            ], indent=2, ensure_ascii=False))
        else:
            for i in infos:
                marker = " *" if i.is_promoted else "  "
                reason = f"  ({i.abandoned_reason})" if i.abandoned_reason else ""
                print(f"{marker} {i.slug:16} {i.status:10}{reason}  {i.file_path}")


if __name__ == "__main__":
    main()
