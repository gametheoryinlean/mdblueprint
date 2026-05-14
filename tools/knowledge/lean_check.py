"""Mechanical prechecks: verify Markdown nodes' Lean references against a Lean index."""
from __future__ import annotations

from pathlib import Path

from tools.knowledge.lean_index import LeanIndex
from tools.knowledge.models import Node
from tools.knowledge.validator import Diagnostic


def check_lean_references(nodes: list[Node], idx: LeanIndex) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    for node in nodes:
        if node.lean is None:
            continue

        nid = node.id
        fp = node.file_path
        is_external = node.kind == "external-theorem"

        # Check modules
        for module in node.lean.modules:
            if module not in idx.modules:
                level = "error" if is_external else "warning"
                diags.append(Diagnostic(
                    level, nid,
                    f"Lean module not found: {module!r}",
                    fp,
                ))

        # Check declarations
        for decl in node.lean.declarations:
            found = False
            if decl in idx.declarations:
                found = True
            else:
                # Try partial match (declaration might be under a namespace)
                for qualified in idx.declarations:
                    if qualified.endswith(f".{decl}") or qualified == decl:
                        found = True
                        break

            if not found:
                level = "error" if is_external else "warning"
                diags.append(Diagnostic(
                    level, nid,
                    f"Lean declaration not found: {decl!r}",
                    fp,
                ))
            else:
                # Check for sorry/admit
                matched_name = decl
                if decl not in idx.declarations:
                    for qualified in idx.declarations:
                        if qualified.endswith(f".{decl}") or qualified == decl:
                            matched_name = qualified
                            break
                if matched_name in idx.declarations:
                    lean_decl = idx.declarations[matched_name]
                    if lean_decl.has_sorry:
                        diags.append(Diagnostic(
                            "warning", nid,
                            f"Lean declaration has sorry/admit: {decl!r} "
                            f"({lean_decl.file}:{lean_decl.line})",
                            fp,
                        ))

    return diags
