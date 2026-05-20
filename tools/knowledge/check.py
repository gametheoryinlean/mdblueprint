"""Comprehensive structural checks for knowledge nodes."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tools.knowledge.config import ProjectConfig, load_project_config
from tools.knowledge.export import home_topic_for_node, leaf_topic_ids_for_node
from tools.knowledge.graph import build_graph
from tools.knowledge.latex_check import check_node_math
from tools.knowledge.lean_check import check_configured_lean_references, check_lean_references
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.models import Node
from tools.knowledge.node_refs import check_node_body_refs
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic, validate_node


def check_knowledge_base(
    root: Path,
    *,
    lean_root: Path | None = None,
    config_path: Path | None = None,
    strict_lean_git: bool = False,
    strict_lean_placeholders: bool = False,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    nodes_dir = root / "nodes"
    staged_dir = root / "staged"
    all_nodes = []
    config = load_project_config(root, config_path)

    project_library = config.sources.library

    require_source_spans = config.sources.require_source_spans

    if nodes_dir.exists():
        for node in scan_directory(nodes_dir):
            diags.extend(validate_node(
                node,
                is_staged_dir=False,
                project_library=project_library,
                require_source_spans=require_source_spans,
            ))
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            diags.extend(_check_topic_registry(node, config))
            all_nodes.append(node)

    if staged_dir.exists():
        for node in scan_directory(staged_dir):
            diags.extend(validate_node(
                node,
                is_staged_dir=True,
                project_library=project_library,
                require_source_spans=require_source_spans,
            ))
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            diags.extend(_check_topic_registry(node, config))
            all_nodes.append(node)

    diags.extend(_check_duplicate_topic_ids(all_nodes, config))

    all_nodes_index: dict[str, Node] = {n.id: n for n in all_nodes}
    for node in all_nodes:
        diags.extend(check_node_body_refs(node, all_nodes_index))

    _, graph_diags = build_graph(all_nodes)
    diags.extend(graph_diags)

    if lean_root is not None and lean_root.is_dir():
        idx = index_lean_project(lean_root)
        diags.extend(check_lean_references(all_nodes, idx))
    elif config.lean.repositories:
        indexes = {
            repo_id: index_lean_project(repo.local_path, repository=repo)
            for repo_id, repo in config.lean.repositories.items()
        }
        dirty = {
            repo_id
            for repo_id, repo in config.lean.repositories.items()
            if _repository_is_dirty(repo.local_path)
        }
        diags.extend(check_configured_lean_references(
            all_nodes,
            config.lean,
            indexes,
            dirty_repositories=dirty,
            strict_dirty=strict_lean_git,
            strict_placeholders=strict_lean_placeholders,
        ))

    return diags


def _repository_is_dirty(path: Path) -> bool:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return False
    return bool(output.strip())


def _check_topic_registry(node: Node, config: ProjectConfig) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if not config.topics:
        return diags
    canonical_ids = {t.id for t in config.topics}
    alias_to_canonical = {alias: t.id for t in config.topics for alias in t.aliases}

    def check_topic(topic: str, field: str) -> None:
        if topic in alias_to_canonical:
            canonical = alias_to_canonical[topic]
            diags.append(Diagnostic(
                "error",
                node.id,
                f"{field} {topic!r} is an alias of canonical topic {canonical!r}; use {canonical!r} instead",
                node.file_path,
            ))
        elif topic not in canonical_ids:
            diags.append(Diagnostic(
                "warning",
                node.id,
                f"{field} {topic!r} is not in the canonical topic registry; add it to mdblueprint.yml topics or use an existing topic",
                node.file_path,
            ))

    check_topic(home_topic_for_node(node), "primary_topic")
    for topic in leaf_topic_ids_for_node(node):
        check_topic(topic, "topics entry")
    return diags


def _check_duplicate_topic_ids(nodes: list[Node], config: ProjectConfig) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    if not config.topics:
        return diags
    canonical_ids = {t.id for t in config.topics}
    alias_to_canonical = {alias: t.id for t in config.topics for alias in t.aliases}
    dir_to_canonical: dict[str, str] = {}
    for node in nodes:
        if not node.id or not node.file_path:
            continue
        home_topic = home_topic_for_node(node)
        canonical = alias_to_canonical.get(home_topic, home_topic)
        if canonical not in canonical_ids:
            continue
        parts = node.file_path.parts
        nodes_idx = None
        for i, p in enumerate(parts):
            if p == "nodes":
                nodes_idx = i
                break
        if nodes_idx is None or len(parts) <= nodes_idx + 2:
            continue
        topic_dir = parts[nodes_idx + 1]
        if topic_dir in dir_to_canonical:
            if dir_to_canonical[topic_dir] != canonical:
                diags.append(Diagnostic(
                    "error",
                    "<top-level>",
                    f"directory {topic_dir!r} contains nodes with different canonical topic prefixes ({dir_to_canonical[topic_dir]!r} and {canonical!r}); each topic directory must map to one canonical topic",
                    None,
                ))
        else:
            dir_to_canonical[topic_dir] = canonical
    return diags


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Structural checks for a Markdown knowledge base",
    )
    parser.add_argument(
        "root", nargs="?", default="docs/knowledge",
        help="path to the knowledge base root (default: docs/knowledge)",
    )
    parser.add_argument(
        "--lean-root", default=None,
        help="path to a Lean project root for reference prechecks",
    )
    parser.add_argument(
        "--config", default=None,
        help="project config path; defaults to <root>/mdblueprint.yml if present",
    )
    parser.add_argument(
        "--strict-lean-git", action="store_true",
        help="treat dirty configured Lean repositories as errors",
    )
    parser.add_argument(
        "--strict-lean-placeholders", action="store_true",
        help="treat Lean sorry/admit diagnostics as errors instead of warnings",
    )
    args = parser.parse_args()

    root = Path(args.root)
    lean_root = Path(args.lean_root) if args.lean_root else None
    config_path = Path(args.config) if args.config else None
    diags = check_knowledge_base(
        root,
        lean_root=lean_root,
        config_path=config_path,
        strict_lean_git=args.strict_lean_git,
        strict_lean_placeholders=args.strict_lean_placeholders,
    )

    errors = [d for d in diags if d.level == "error"]
    warnings = [d for d in diags if d.level == "warning"]

    for d in sorted(diags, key=lambda d: (d.level, str(d.file_path or ""))):
        print(d)

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
