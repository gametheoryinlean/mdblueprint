"""Mechanical prechecks: verify Markdown nodes' Lean references against a Lean index."""
from __future__ import annotations

from tools.knowledge.config import LeanConfig
from tools.knowledge.lean_index import LeanIndex
from tools.knowledge.models import Node
from tools.knowledge.validator import Diagnostic


def _matching_declarations(decl: str, idx: LeanIndex) -> list[str]:
    if decl in idx.declarations:
        return [decl]
    return [
        qualified
        for qualified in idx.declarations
        if qualified.endswith(f".{decl}") or qualified == decl
    ]


def _context(repository_id: str | None) -> str:
    return f" in repository {repository_id!r}" if repository_id else ""


def check_lean_references(
    nodes: list[Node],
    idx: LeanIndex,
    *,
    repository_id: str | None = None,
    strict_ambiguity: bool = False,
    strict_placeholders: bool = False,
) -> list[Diagnostic]:
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
                    f"Lean module not found{_context(repository_id)}: {module!r}",
                    fp,
                ))

        # Check declarations
        for decl in node.lean.declarations:
            matches = _matching_declarations(decl, idx)

            if len(matches) > 1 and strict_ambiguity:
                diags.append(Diagnostic(
                    "error", nid,
                    f"ambiguous Lean declaration{_context(repository_id)}: {decl!r} "
                    f"matches {', '.join(sorted(matches))}",
                    fp,
                ))
                continue

            if not matches:
                level = "error" if is_external else "warning"
                diags.append(Diagnostic(
                    level, nid,
                    f"Lean declaration not found{_context(repository_id)}: {decl!r}",
                    fp,
                ))
            else:
                # Check for sorry/admit
                matched_name = matches[0]
                if matched_name in idx.declarations:
                    lean_decl = idx.declarations[matched_name]
                    if lean_decl.has_sorry:
                        level = "error" if strict_placeholders else "warning"
                        diags.append(Diagnostic(
                            level, nid,
                            f"Lean declaration has sorry/admit{_context(repository_id)}: {decl!r} "
                            f"({lean_decl.file}:{lean_decl.line})",
                            fp,
                        ))

    return diags


def check_configured_lean_references(
    nodes: list[Node],
    lean_config: LeanConfig,
    indexes: dict[str, LeanIndex],
    *,
    dirty_repositories: set[str] | None = None,
    strict_dirty: bool = False,
    strict_placeholders: bool = False,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    dirty_repositories = dirty_repositories or set()
    for repo_id in sorted(dirty_repositories):
        level = "error" if strict_dirty else "warning"
        diags.append(Diagnostic(
            level,
            f"lean.repository.{repo_id}",
            f"Lean repository {repo_id!r} has uncommitted or untracked files",
        ))

    for node in nodes:
        if node.lean is None:
            continue
        repo_id = node.lean.repository or lean_config.default_repository
        if repo_id is None:
            diags.append(Diagnostic(
                "error",
                node.id,
                "Lean repository not specified and lean.default_repository is not configured",
                node.file_path,
            ))
            continue
        if repo_id not in lean_config.repositories:
            diags.append(Diagnostic(
                "error",
                node.id,
                f"Lean repository not configured: {repo_id!r}",
                node.file_path,
            ))
            continue
        diags.extend(check_lean_references(
            [node],
            indexes[repo_id],
            repository_id=repo_id,
            strict_ambiguity=True,
            strict_placeholders=strict_placeholders,
        ))
    return diags
