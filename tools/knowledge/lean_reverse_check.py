"""Cross-check forward (MD → Lean) and reverse (Lean → MD) links.

This module reports drift between the two halves of the link surface:

- Forward map: for every node N with `lean.declarations`, every entry
  is an edge `N → decl`.
- Reverse map: for every Lean declaration with a `Blueprint:` marker,
  every node id in the marker is an edge `decl → N`.

The four diagnostic categories surfaced by `check_reverse_links`:

| Category         | Meaning                                          | Severity |
|------------------|--------------------------------------------------|----------|
| OK               | both directions agree                            | (silent) |
| MD-only          | MD points at decl, decl has no Blueprint marker  | info     |
| Lean-only        | decl claims node, node doesn't list the decl     | warning  |
| Cross-mismatch   | both directions exist, sets disagree             | error    |

Exit code is non-zero iff any cross-mismatch is found, so the CLI is
suitable as a CI gate.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex, index_lean_project
from tools.knowledge.models import Node


@dataclass(frozen=True)
class ReverseDiagnostic:
    category: str  # "ok" | "md_only" | "lean_only" | "cross_mismatch"
    severity: str  # "info" | "warning" | "error"
    repository_id: str
    declaration: str
    node_id: str | None
    message: str

    def format(self) -> str:
        node_repr = self.node_id if self.node_id else "-"
        return (
            f"[{self.severity.upper()}] {self.category} "
            f"({self.repository_id}::{self.declaration} ~ {node_repr}): "
            f"{self.message}"
        )


def _forward_edges(nodes: Iterable[Node]) -> dict[str, set[tuple[str, str]]]:
    """Return repo_id -> set[(qualified_declaration, node_id)]."""
    edges: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for node in nodes:
        if node.lean is None or not node.lean.declarations:
            continue
        repo = node.lean.repository
        if not repo:
            # Without a repo binding we can't pair the edge with a Lean
            # index; skip silently — this is reported elsewhere.
            continue
        for decl in node.lean.declarations:
            edges[repo].add((decl, node.id))
    return edges


def _reverse_edges(
    indexes: dict[str, LeanIndex],
) -> dict[str, set[tuple[str, str]]]:
    """Return repo_id -> set[(qualified_declaration, node_id)] derived
    from Blueprint: markers on indexed declarations."""
    edges: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for repo_id, idx in indexes.items():
        for qname, decl in idx.declarations.items():
            for node_id in decl.blueprint_nodes:
                edges[repo_id].add((qname, node_id))
    return edges


def _matching_declarations(decl: str, idx: LeanIndex) -> list[str]:
    """Same suffix-tolerant matcher used by lean_check / renderer."""
    if decl in idx.declarations:
        return [decl]
    return [
        qualified
        for qualified in idx.declarations
        if qualified.endswith(f".{decl}") or qualified == decl
    ]


def check_reverse_links(
    nodes: list[Node],
    indexes: dict[str, LeanIndex],
) -> list[ReverseDiagnostic]:
    """Compare forward and reverse edge sets, emit per-edge diagnostics."""
    diags: list[ReverseDiagnostic] = []

    forward_raw = _forward_edges(nodes)
    reverse = _reverse_edges(indexes)

    # Normalise forward edges to the resolved-qualified-name basis so
    # that MD shorthand (e.g. `bar` matching `Foo.bar`) compares
    # apples-to-apples against the reverse map. Unresolvable entries
    # (no match in the index, or ambiguous) are passed through as-is;
    # those are surfaced separately by `lean_check`.
    forward: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for repo_id, edges in forward_raw.items():
        idx = indexes.get(repo_id)
        for decl, node_id in edges:
            if idx is None:
                forward[repo_id].add((decl, node_id))
                continue
            matches = _matching_declarations(decl, idx)
            if len(matches) == 1:
                forward[repo_id].add((matches[0], node_id))
            else:
                # Unresolved / ambiguous — preserve original name so
                # the cross-check still tracks it; lean_check will
                # warn separately.
                forward[repo_id].add((decl, node_id))

    repos = set(forward.keys()) | set(reverse.keys())
    for repo_id in sorted(repos):
        fwd = forward.get(repo_id, set())
        rev = reverse.get(repo_id, set())

        # Cross-mismatch: same declaration, both maps non-empty, but
        # the node-id sets disagree at the declaration level.
        fwd_by_decl: dict[str, set[str]] = defaultdict(set)
        for decl, node_id in fwd:
            fwd_by_decl[decl].add(node_id)
        rev_by_decl: dict[str, set[str]] = defaultdict(set)
        for decl, node_id in rev:
            rev_by_decl[decl].add(node_id)

        shared_decls = set(fwd_by_decl) & set(rev_by_decl)
        for decl in sorted(shared_decls):
            f_set = fwd_by_decl[decl]
            r_set = rev_by_decl[decl]
            common = f_set & r_set
            for node in sorted(common):
                diags.append(ReverseDiagnostic(
                    category="ok",
                    severity="info",
                    repository_id=repo_id,
                    declaration=decl,
                    node_id=node,
                    message="forward + reverse both present",
                ))
            md_only_for_decl = f_set - r_set
            lean_only_for_decl = r_set - f_set
            if md_only_for_decl and lean_only_for_decl:
                # Both maps name node-ids for this declaration, but
                # they disagree -> cross-mismatch.
                diags.append(ReverseDiagnostic(
                    category="cross_mismatch",
                    severity="error",
                    repository_id=repo_id,
                    declaration=decl,
                    node_id=None,
                    message=(
                        f"MD says: {sorted(f_set)}; Lean says: {sorted(r_set)}"
                    ),
                ))
            else:
                # Otherwise treat the leftovers as one-sided.
                for node in sorted(md_only_for_decl):
                    diags.append(ReverseDiagnostic(
                        category="md_only",
                        severity="info",
                        repository_id=repo_id,
                        declaration=decl,
                        node_id=node,
                        message="MD references this decl; no Blueprint: marker on the Lean side",
                    ))
                for node in sorted(lean_only_for_decl):
                    diags.append(ReverseDiagnostic(
                        category="lean_only",
                        severity="warning",
                        repository_id=repo_id,
                        declaration=decl,
                        node_id=node,
                        message="Lean decl self-identifies; MD node lacks this declaration",
                    ))

        # Declarations that only appear in one map at all.
        md_decls_only = set(fwd_by_decl) - shared_decls
        lean_decls_only = set(rev_by_decl) - shared_decls
        for decl in sorted(md_decls_only):
            for node in sorted(fwd_by_decl[decl]):
                diags.append(ReverseDiagnostic(
                    category="md_only",
                    severity="info",
                    repository_id=repo_id,
                    declaration=decl,
                    node_id=node,
                    message="MD references this decl; no Blueprint: marker on the Lean side",
                ))
        for decl in sorted(lean_decls_only):
            for node in sorted(rev_by_decl[decl]):
                diags.append(ReverseDiagnostic(
                    category="lean_only",
                    severity="warning",
                    repository_id=repo_id,
                    declaration=decl,
                    node_id=node,
                    message="Lean decl self-identifies; MD node lacks this declaration",
                ))

    return diags


def summarise(diags: list[ReverseDiagnostic]) -> dict[str, int]:
    counts = {"ok": 0, "md_only": 0, "lean_only": 0, "cross_mismatch": 0}
    for d in diags:
        counts[d.category] = counts.get(d.category, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-check MD lean.declarations vs Lean Blueprint: markers.",
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument(
        "--show",
        choices=["all", "issues", "errors"],
        default="issues",
        help="What to print: all categories, issues (md_only + lean_only + "
             "cross_mismatch, default), or errors only (cross_mismatch).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any lean_only warnings are present "
             "(cross_mismatch always triggers non-zero exit).",
    )
    args = parser.parse_args(argv)

    ctx = KnowledgeContext.load(args.knowledge_root)
    # `KnowledgeContext.load(..., lean=True)` skips indexing when no MD
    # node has a `lean:` block. The reverse-check needs the Lean index
    # regardless (an entire repo can be self-marked but have no MD
    # back-refs yet), so we always build the indexes here directly.
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    diags = check_reverse_links(list(ctx.nodes_by_id.values()), indexes)

    show = args.show
    for d in diags:
        if show == "errors" and d.category != "cross_mismatch":
            continue
        if show == "issues" and d.category == "ok":
            continue
        print(d.format())

    counts = summarise(diags)
    print(
        f"\n{counts['ok']} ok, "
        f"{counts['md_only']} md-only, "
        f"{counts['lean_only']} lean-only, "
        f"{counts['cross_mismatch']} cross-mismatch."
    )

    exit_code = 0
    if counts["cross_mismatch"] > 0:
        exit_code = 2
    elif args.strict and counts["lean_only"] > 0:
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
