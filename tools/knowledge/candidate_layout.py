"""Cross-file invariants for the multi-candidate proof layout (issue #159).

A canonical theorem with multiple proof attempts lives as a directory::

    nodes/<topic>/<local_id>/
      canonical.md                  # statement + promoted-proof pointer
      candidates/
        cand_a.md                   # full proof attempt (status: promoted)
        cand_b.md                   # full proof attempt (status: abandoned)

This module is the single source of truth for:

- recovering a canonical's directory from a node (``canonical_dir``);
- grouping a node list into canonical ↔ candidate clusters
  (``discover_canonical_groups``);
- resolving which node holds the *active* proof for a canonical
  (``canonical_proof_source``);
- finding the proof-block boundary in a body (``proof_block_start``);
- validating the cross-file relationship (``validate_canonical_groups``).

Per-node schema rules (slug regex, id composition, staged rejection) live
in ``validator.validate_node``; this module assumes those have already run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.knowledge.models import Node
from tools.knowledge.validator import Diagnostic

# Proof-block markers. Kept in sync with ``admit._has_proof_block``, which
# imports these so there is exactly one definition of the boundary.
PROOF_MARKERS: tuple[str, ...] = ("*Proof.*", "**Proof.**")


def proof_block_start(body: str) -> int | None:
    """Return the index of the earliest proof marker in ``body``, or None."""
    positions = [body.find(m) for m in PROOF_MARKERS]
    found = [p for p in positions if p != -1]
    return min(found) if found else None


def statement_segment(body: str) -> str:
    """Return the portion of ``body`` before the proof block (or all of it)."""
    idx = proof_block_start(body)
    return body if idx is None else body[:idx]


def normalize_statement(text: str) -> str:
    """Collapse whitespace and strip trailing punctuation for comparison."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed.rstrip(".,;:!? ")


_LEADING_H1_RE = re.compile(r"\A\s*#\s+[^\n]*\n?")


def comparable_statement(body: str) -> str:
    """Normalised statement used for canonical ↔ candidate equality.

    Drops a single leading H1 heading (the display title legitimately
    differs between a canonical and its candidates, e.g. "SPE" vs
    "SPE (cand_a)") and everything from the proof marker onward, then
    normalises whitespace and trailing punctuation.
    """
    seg = statement_segment(body)
    seg = _LEADING_H1_RE.sub("", seg, count=1)
    return normalize_statement(seg)


@dataclass
class CanonicalGroup:
    """A canonical (multi-layout) node together with its candidate files."""

    canonical: Node
    candidates: list[Node] = field(default_factory=list)
    dir_path: Path | None = None


def canonical_dir(node: Node) -> Path | None:
    """Recover the canonical's directory from a canonical or candidate node.

    - A canonical (``candidate_layout == "multi"``) lives at
      ``<topic>/<local_id>/canonical.md`` → its dir is ``file_path.parent``.
    - A candidate (``candidate_of`` set) lives at
      ``<topic>/<local_id>/candidates/<slug>.md`` → its dir is
      ``file_path.parent.parent``.
    - Any other node returns ``None``.
    """
    if node.file_path is None:
        return None
    if node.candidate_layout == "multi":
        return node.file_path.parent
    if node.candidate_of is not None:
        return node.file_path.parent.parent
    return None


def discover_canonical_groups(nodes: list[Node]) -> list[CanonicalGroup]:
    """Group nodes into canonical ↔ candidate clusters.

    Only nodes with ``candidate_layout == "multi"`` seed a group. Candidates
    are matched to their canonical by ``candidate_of``. Candidates with no
    matching multi-canonical are *not* placed in any group;
    ``validate_canonical_groups`` flags them via ``nodes_by_id``.
    """
    groups: dict[str, CanonicalGroup] = {}
    for node in nodes:
        if node.candidate_layout == "multi":
            groups[node.id] = CanonicalGroup(
                canonical=node, candidates=[], dir_path=canonical_dir(node)
            )
    for node in nodes:
        if node.candidate_of is None:
            continue
        group = groups.get(node.candidate_of)
        if group is not None:
            group.candidates.append(node)
    for group in groups.values():
        group.candidates.sort(key=lambda n: n.candidate_slug or n.id)
    return sorted(groups.values(), key=lambda g: g.canonical.id)


def canonical_proof_source(
    canonical_id: str,
    nodes_by_id: dict[str, Node],
    groups_by_canonical: dict[str, CanonicalGroup] | None = None,
) -> Node | None:
    """Return the node holding the active proof for ``canonical_id``.

    - Single-file canonical → the canonical node itself.
    - Multi-candidate canonical with a promoted sibling → that sibling.
    - Multi-candidate canonical with no promoted sibling yet → the canonical
      (its ``verification.proof`` is still pending).
    """
    canonical = nodes_by_id.get(canonical_id)
    if canonical is None:
        return None
    if canonical.candidate_layout != "multi":
        return canonical
    group = (groups_by_canonical or {}).get(canonical_id)
    candidates = group.candidates if group else [
        n for n in nodes_by_id.values() if n.candidate_of == canonical_id
    ]
    for cand in candidates:
        if cand.status == "promoted":
            return cand
    return canonical


def validate_canonical_groups(
    groups: list[CanonicalGroup],
    nodes_by_id: dict[str, Node],
) -> list[Diagnostic]:
    """Enforce the cross-file invariants between canonicals and candidates."""
    diags: list[Diagnostic] = []
    group_by_canonical = {g.canonical.id: g for g in groups}

    # 1. Every candidate's candidate_of must resolve to a multi-canonical.
    for node in sorted(nodes_by_id.values(), key=lambda n: n.id):
        if node.candidate_of is None:
            continue
        target = nodes_by_id.get(node.candidate_of)
        if target is None:
            diags.append(Diagnostic(
                "error", node.id,
                f"candidate_of references unknown canonical "
                f"{node.candidate_of!r}",
                node.file_path,
            ))
            continue
        if target.candidate_layout != "multi":
            diags.append(Diagnostic(
                "error", node.id,
                f"candidate_of {node.candidate_of!r} is not a multi-candidate "
                f"canonical (no canonical.md with candidate_layout: multi)",
                node.file_path,
            ))

    # 2. Per-group invariants.
    for group in groups:
        diags.extend(_validate_group(group, group_by_canonical))

    return diags


def _validate_group(
    group: CanonicalGroup,
    group_by_canonical: dict[str, CanonicalGroup],
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    canonical = group.canonical
    cid = canonical.id
    cdir = group.dir_path

    def err(node: Node, msg: str) -> None:
        diags.append(Diagnostic("error", node.id, msg, node.file_path))

    # File layout: canonical must be named canonical.md.
    if canonical.file_path is not None and canonical.file_path.name != "canonical.md":
        err(canonical, "multi-candidate canonical must be named canonical.md")

    # candidates field must equal the discovered slug list.
    discovered = sorted(c.candidate_slug for c in group.candidates if c.candidate_slug)
    declared = sorted(canonical.candidates)
    if declared != discovered:
        err(
            canonical,
            f"candidates field {declared} does not match candidate files "
            f"on disk {discovered}",
        )

    # Promoted-sibling uniqueness.
    promoted = [c for c in group.candidates if c.status == "promoted"]
    if len(promoted) > 1:
        paths = ", ".join(str(c.file_path) for c in promoted)
        err(
            canonical,
            f"multiple promoted candidates for {cid!r}; at most one allowed "
            f"({paths})",
        )

    # promoted_candidate field consistency.
    pc = canonical.promoted_candidate
    if pc is None:
        if promoted:
            err(
                canonical,
                f"promoted_candidate is null but candidate "
                f"{promoted[0].candidate_slug!r} has status: promoted",
            )
    else:
        match = [c for c in group.candidates if c.candidate_slug == pc]
        if not match:
            err(
                canonical,
                f"promoted_candidate {pc!r} names no candidate file",
            )
        elif match[0].status != "promoted":
            err(
                canonical,
                f"promoted_candidate {pc!r} has status {match[0].status!r}, "
                f"expected 'promoted'",
            )

    # Per-candidate checks.
    canonical_stmt = comparable_statement(canonical.body)
    for cand in group.candidates:
        # File location.
        if cdir is not None and cand.file_path is not None and cand.candidate_slug:
            expected = cdir / "candidates" / f"{cand.candidate_slug}.md"
            if cand.file_path != expected:
                err(
                    cand,
                    f"candidate must live at {expected}, found at "
                    f"{cand.file_path}",
                )
        # Kind equality.
        if cand.kind != canonical.kind:
            err(
                cand,
                f"candidate kind {cand.kind!r} must equal canonical kind "
                f"{canonical.kind!r}",
            )
        # Statement equality.
        cand_stmt = comparable_statement(cand.body)
        if cand_stmt != canonical_stmt:
            err(
                cand,
                f"candidate statement diverges from canonical {cid!r}; "
                f"the statement segment must match after normalisation",
            )

    return diags
