"""Promote theorem status to 'proved' when an attached plan provides a complete proof.

Scans a knowledge directory, finds theorem-like nodes whose attached proof
plans satisfy the "plan provides proof" condition, and rewrites their YAML
frontmatter to set ``status: proved`` and ``proved_via_plan: <plan_id>``.

Idempotent: re-running on an already-promoted file makes no change. Refuses
to run if the knowledge base has schema errors or cycles.

Usage:
    uv run python -m tools.knowledge.promote_via_plan docs/knowledge
    uv run python -m tools.knowledge.promote_via_plan docs/knowledge --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.knowledge.blueprint_view import plan_provides_proof
from tools.knowledge.config import load_project_config
from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.models import PROOF_PLAN_TARGET_KINDS, Node
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import validate_node


def _canonical_plan(target_id: str, g: KnowledgeGraph) -> str | None:
    """Pick the plan that should be recorded as the source of the proof.

    Preference order:
      1. plan_status == "selected" (lexicographically smallest plan id if tied)
      2. any qualifying plan (lexicographically smallest plan id)
    """
    candidates = [
        plan_id
        for plan_id in g.proof_plans_by_target.get(target_id, [])
        if plan_provides_proof(plan_id, g)
    ]
    if not candidates:
        return None
    selected = sorted(
        plan_id for plan_id in candidates
        if g.nodes[plan_id].plan_status == "selected"
    )
    if selected:
        return selected[0]
    return sorted(candidates)[0]


def _rewrite_frontmatter(text: str, *, plan_id: str) -> str:
    """Set ``status: proved`` and ``proved_via_plan: <plan_id>`` in-place.

    Preserves all other lines, ordering, comments, and blank lines inside
    the frontmatter. Inserts ``proved_via_plan`` immediately after the
    ``status`` line when the field is absent.
    """
    lines = text.split("\n")
    fm_start = fm_end = None
    for index, line in enumerate(lines):
        if line.strip() == "---":
            if fm_start is None:
                fm_start = index
            else:
                fm_end = index
                break
    if fm_start is None or fm_end is None:
        raise ValueError("frontmatter delimiters '---' not found")

    new_fm: list[str] = []
    status_index_in_new: int | None = None
    plan_seen = False
    for line in lines[fm_start + 1:fm_end]:
        stripped = line.lstrip()
        if stripped.startswith("status:"):
            new_fm.append("status: proved")
            status_index_in_new = len(new_fm) - 1
        elif stripped.startswith("proved_via_plan:"):
            new_fm.append(f"proved_via_plan: {plan_id}")
            plan_seen = True
        else:
            new_fm.append(line)

    if not plan_seen:
        if status_index_in_new is None:
            raise ValueError("'status:' line not found in frontmatter")
        new_fm.insert(status_index_in_new + 1, f"proved_via_plan: {plan_id}")

    result = lines[:fm_start + 1] + new_fm + lines[fm_end:]
    return "\n".join(result)


def _has_blocking_diagnostics(diags: list) -> bool:
    return any(d.level == "error" for d in diags)


def _collect_promotion_candidates(
    nodes: list[Node],
    knowledge_root: Path | None = None,
) -> tuple[list[tuple[Node, str]], list[str], KnowledgeGraph]:
    """Return (candidates, blocking_error_messages, graph).

    A candidate is a tuple ``(node, chosen_plan_id)`` where ``node`` is a
    theorem-like node not yet ``status: proved`` whose attached plans
    include at least one that supplies a complete proof.
    """
    if knowledge_root is not None and (knowledge_root / "mdblueprint.yml").exists():
        config = load_project_config(knowledge_root)
        project_library = config.sources.library
        require_source_spans = config.sources.require_source_spans
    else:
        project_library = None
        require_source_spans = False

    schema_errors: list[str] = []
    for node in nodes:
        if node.file_path is None:
            continue
        is_staged_dir = "staged" in node.file_path.parts
        for diag in validate_node(
            node,
            is_staged_dir=is_staged_dir,
            project_library=project_library,
            require_source_spans=require_source_spans,
        ):
            if diag.level == "error":
                schema_errors.append(f"{node.file_path}: {diag.message}")
    if schema_errors:
        return [], schema_errors, KnowledgeGraph()

    g, build_diags = build_graph(nodes)
    build_errors = [
        f"{(d.file_path or '?')}: {d.message}"
        for d in build_diags
        if d.level == "error"
    ]
    if build_errors:
        return [], build_errors, g

    candidates: list[tuple[Node, str]] = []
    for node in sorted(g.nodes.values(), key=lambda n: n.id):
        if node.kind not in PROOF_PLAN_TARGET_KINDS:
            continue
        if node.status == "proved":
            continue
        plan_id = _canonical_plan(node.id, g)
        if plan_id is not None:
            candidates.append((node, plan_id))
    return candidates, [], g


def _scan_knowledge_nodes(knowledge_root: Path) -> list[Node]:
    """Scan only the canonical knowledge subdirectories.

    Mirrors check.py: review/request/audit artifacts under other subtrees
    are not part of the knowledge graph and should not be validated as
    nodes.
    """
    nodes: list[Node] = []
    for subdir in ("nodes", "staged"):
        path = knowledge_root / subdir
        if path.exists():
            nodes.extend(scan_directory(path))
    return nodes


def promote(knowledge_root: Path, *, dry_run: bool) -> int:
    nodes = _scan_knowledge_nodes(knowledge_root)
    candidates, errors, _ = _collect_promotion_candidates(nodes, knowledge_root)

    if errors:
        print("Refusing to promote: knowledge base has blocking errors", file=sys.stderr)
        for error in errors[:20]:
            print(f"  {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more", file=sys.stderr)
        return 1

    if not candidates:
        print("No theorems are ready for proved_via_plan promotion. Nothing to do.")
        return 0

    print(f"{'[dry-run] ' if dry_run else ''}Promoting {len(candidates)} theorem(s):")
    for node, plan_id in candidates:
        relative = (
            node.file_path.relative_to(knowledge_root)
            if node.file_path and knowledge_root in node.file_path.parents
            else node.file_path
        )
        print(f"  {node.id}: status {node.status!r} -> 'proved', via plan {plan_id}")
        print(f"    file: {relative}")
        if dry_run:
            continue
        original = node.file_path.read_text(encoding="utf-8")
        rewritten = _rewrite_frontmatter(original, plan_id=plan_id)
        if rewritten != original:
            node.file_path.write_text(rewritten, encoding="utf-8")

    if dry_run:
        print(f"[dry-run] {len(candidates)} file(s) would be modified. No writes performed.")
    else:
        print(f"Wrote {len(candidates)} file(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "knowledge_root",
        type=Path,
        help="Path to the knowledge directory (e.g. docs/knowledge)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without modifying any files",
    )
    args = parser.parse_args(argv)

    knowledge_root = args.knowledge_root.resolve()
    if not knowledge_root.is_dir():
        print(f"not a directory: {knowledge_root}", file=sys.stderr)
        return 2
    return promote(knowledge_root, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
