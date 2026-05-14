"""Comprehensive structural checks for knowledge nodes."""
from __future__ import annotations

import sys
from pathlib import Path

from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory, parse_file
from tools.knowledge.validator import Diagnostic, validate_node


def check_knowledge_base(root: Path) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    nodes_dir = root / "nodes"
    staged_dir = root / "staged"
    all_nodes = []

    if nodes_dir.exists():
        for node in scan_directory(nodes_dir):
            node_diags = validate_node(node, is_staged_dir=False)
            diags.extend(node_diags)
            all_nodes.append(node)

    if staged_dir.exists():
        for node in scan_directory(staged_dir):
            node_diags = validate_node(node, is_staged_dir=True)
            diags.extend(node_diags)
            all_nodes.append(node)

    _, graph_diags = build_graph(all_nodes)
    diags.extend(graph_diags)

    return diags


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/knowledge")
    diags = check_knowledge_base(root)

    errors = [d for d in diags if d.level == "error"]
    warnings = [d for d in diags if d.level == "warning"]

    for d in sorted(diags, key=lambda d: (d.level, str(d.file_path or ""))):
        print(d)

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
