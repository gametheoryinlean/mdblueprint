"""Tier 1 auto-fix: promote `lean_only` reverse-check warnings into
MD ``lean.declarations`` entries.

When a Lean declaration self-identifies via a ``Blueprint:`` marker
pointing at node ``X``, but node ``X``'s frontmatter doesn't list
that declaration in ``lean.declarations``, the reverse-check emits
a ``lean_only`` warning. This tool collects those warnings and
proposes MD frontmatter patches that add the missing entries.

It is a "mechanical" autofix: only when the Lean side explicitly
states ``Blueprint: X``, we trust it. Cross-mismatch and md-only
diagnostics are *not* touched — those require human judgement.

Run with ``--apply`` to actually mutate the files; without it, only
a dry-run diff is printed.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.lean_linking import _split_frontmatter
from tools.knowledge.lean_reverse_check import check_reverse_links
from tools.knowledge.models import Node


@dataclass(frozen=True)
class NodePatch:
    """A planned patch for one node file."""
    node_id: str
    file_path: Path
    repository_id: str
    add_declarations: tuple[str, ...]
    add_modules: tuple[str, ...]


def _existing_lean_block(fm: dict) -> dict:
    """Return the current `lean:` mapping, or {} if missing/empty."""
    lean = fm.get("lean")
    return lean if isinstance(lean, dict) else {}


def _planned_patches(
    nodes: list[Node],
    indexes: dict,
    *,
    default_repository: str | None,
) -> list[NodePatch]:
    """Collect lean_only diagnostics → group by target node → propose
    the additions needed to clear them.
    """
    diags = check_reverse_links(
        nodes,
        indexes,
        default_repository=default_repository,
    )
    by_node: dict[str, list] = defaultdict(list)
    for d in diags:
        if d.category != "lean_only":
            continue
        if d.node_id is None:
            continue
        by_node[d.node_id].append(d)

    nodes_by_id = {n.id: n for n in nodes}
    patches: list[NodePatch] = []
    for node_id, ds in sorted(by_node.items()):
        node = nodes_by_id.get(node_id)
        if node is None or node.file_path is None:
            # Lean self-identifies as backing a node that doesn't exist
            # in MD — that's a different kind of drift (likely a typo
            # in the Lean Blueprint marker). Skip silently here.
            continue
        # Use the repository id from the diag; they all share the same
        # value per (node_id, repo) but lean_only never mixes repos for
        # one (qualified, node) pair, so the first wins.
        repo_id = ds[0].repository_id
        existing = _existing_lean_block(_frontmatter(node))
        existing_decls = set(existing.get("declarations") or [])
        existing_modules = set(existing.get("modules") or [])
        add_decls: list[str] = []
        for d in ds:
            if d.declaration in existing_decls:
                continue
            add_decls.append(d.declaration)
            existing_decls.add(d.declaration)
        # We also derive the module for each new decl so the node's
        # `lean.modules` list grows in sync (helpful for module-level
        # links in the rendered modal).
        add_mods: list[str] = []
        repo_idx = indexes.get(repo_id)
        if repo_idx is not None:
            for decl in add_decls:
                lean_decl = repo_idx.declarations.get(decl)
                if lean_decl is None or lean_decl.module is None:
                    continue
                if lean_decl.module in existing_modules:
                    continue
                add_mods.append(lean_decl.module)
                existing_modules.add(lean_decl.module)
        if not add_decls and not add_mods:
            continue
        patches.append(NodePatch(
            node_id=node_id,
            file_path=node.file_path,
            repository_id=repo_id,
            add_declarations=tuple(add_decls),
            add_modules=tuple(add_mods),
        ))
    return patches


def _frontmatter(node: Node) -> dict:
    if node.file_path is None:
        return {}
    text = node.file_path.read_text(encoding="utf-8")
    fm, _ = _split_frontmatter(text)
    return fm


def _render_patched_file(file_path: Path, patch: NodePatch) -> str:
    """Apply the patch to the on-disk file content; return the new text."""
    text = file_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    lean = fm.get("lean")
    if not isinstance(lean, dict):
        lean = {}
    # Repository comes first by convention (matches existing render).
    if "repository" not in lean and patch.repository_id:
        lean = {"repository": patch.repository_id, **lean}
    modules = list(lean.get("modules") or [])
    for m in patch.add_modules:
        if m not in modules:
            modules.append(m)
    if modules:
        lean["modules"] = modules
    declarations = list(lean.get("declarations") or [])
    for d in patch.add_declarations:
        if d not in declarations:
            declarations.append(d)
    lean["declarations"] = declarations
    fm["lean"] = lean
    rendered = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{rendered}\n---\n{body}"


def _diff(before: str, after: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=label,
            tofile=label,
            n=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tier 1 auto-fix: promote lean_only reverse-check "
                    "warnings into MD lean.declarations entries.",
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write patches to disk. Without --apply, prints a dry-run diff.",
    )
    args = parser.parse_args(argv)

    ctx = KnowledgeContext.load(args.knowledge_root)
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    patches = _planned_patches(
        list(ctx.nodes_by_id.values()),
        indexes,
        default_repository=ctx.config.lean.default_repository,
    )

    if not patches:
        print("No patches to apply (no lean_only warnings).")
        return 0

    total_decls = sum(len(p.add_declarations) for p in patches)
    total_mods = sum(len(p.add_modules) for p in patches)
    summary = (
        f"{len(patches)} node(s) affected; "
        f"+{total_decls} declaration(s), +{total_mods} module(s)"
    )

    for patch in patches:
        before = patch.file_path.read_text(encoding="utf-8")
        after = _render_patched_file(patch.file_path, patch)
        label = str(
            patch.file_path.relative_to(args.knowledge_root)
            if patch.file_path.is_relative_to(args.knowledge_root)
            else patch.file_path
        )
        print(_diff(before, after, label), end="")
        if args.apply:
            patch.file_path.write_text(after, encoding="utf-8")

    print()
    print(summary)
    if not args.apply:
        print("Dry run — re-run with --apply to write these changes.")
    else:
        print("Applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
