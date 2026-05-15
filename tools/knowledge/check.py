"""Comprehensive structural checks for knowledge nodes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.knowledge.config import load_project_config
from tools.knowledge.graph import build_graph
from tools.knowledge.latex_check import check_node_math
from tools.knowledge.lean_check import check_lean_references
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic, validate_node


def check_knowledge_base(
    root: Path, *, lean_root: Path | None = None, config_path: Path | None = None
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    nodes_dir = root / "nodes"
    staged_dir = root / "staged"
    all_nodes = []
    config = load_project_config(root, config_path)

    if nodes_dir.exists():
        for node in scan_directory(nodes_dir):
            diags.extend(validate_node(node, is_staged_dir=False))
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            all_nodes.append(node)

    if staged_dir.exists():
        for node in scan_directory(staged_dir):
            diags.extend(validate_node(node, is_staged_dir=True))
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            all_nodes.append(node)

    _, graph_diags = build_graph(all_nodes)
    diags.extend(graph_diags)

    if lean_root is not None and lean_root.is_dir():
        idx = index_lean_project(lean_root)
        diags.extend(check_lean_references(all_nodes, idx))

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
    args = parser.parse_args()

    root = Path(args.root)
    lean_root = Path(args.lean_root) if args.lean_root else None
    config_path = Path(args.config) if args.config else None
    diags = check_knowledge_base(root, lean_root=lean_root, config_path=config_path)

    errors = [d for d in diags if d.level == "error"]
    warnings = [d for d in diags if d.level == "warning"]

    for d in sorted(diags, key=lambda d: (d.level, str(d.file_path or ""))):
        print(d)

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
