"""Build bounded KB-only context bundles for agent reasoning."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.knowledge.export import leaf_topic_ids_for_node
from tools.knowledge.graph import build_graph, topological_sort
from tools.knowledge.models import Node
from tools.knowledge.parser import scan_directory


FORBIDDEN_INPUTS = [
    "Lean source",
    "source artifacts",
    "implementation files",
    "internet",
    "unstated model memory",
]


def _load_nodes(root: Path, *, include_staged: bool) -> tuple[list[Node], set[str]]:
    nodes: list[Node] = []
    staged_ids: set[str] = set()
    nodes_dir = root / "nodes"
    staged_dir = root / "staged"
    if nodes_dir.exists():
        nodes.extend(scan_directory(nodes_dir))
    if include_staged and staged_dir.exists():
        staged = scan_directory(staged_dir)
        staged_ids = {node.id for node in staged}
        nodes.extend(staged)
    return nodes, staged_ids


def _closure(target_id: str, nodes_by_id: dict[str, Node]) -> set[str]:
    selected: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in selected or node_id not in nodes_by_id:
            return
        selected.add(node_id)
        for dep_id in nodes_by_id[node_id].uses:
            visit(dep_id)

    visit(target_id)
    return selected


def _topic_selected(topic: str, nodes: list[Node]) -> set[str]:
    return {
        node.id
        for node in nodes
        if topic in leaf_topic_ids_for_node(node)
        or any(member.startswith(topic + ".") for member in leaf_topic_ids_for_node(node))
    }


def _node_payload(node: Node, *, staged_ids: set[str]) -> dict:
    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "primary_topic": node.primary_topic,
        "topics": leaf_topic_ids_for_node(node),
        "uses": node.uses,
        "evidence": "non-admitted" if node.id in staged_ids else "admitted",
        "source_path": str(node.file_path) if node.file_path else None,
        "body": node.body,
    }


def build_context_pack(
    root: Path,
    *,
    target_id: str | None = None,
    topic: str | None = None,
    include_staged: bool = False,
) -> dict:
    if not target_id and not topic:
        raise ValueError("context pack requires --target or --topic")
    nodes, staged_ids = _load_nodes(root, include_staged=include_staged)
    nodes_by_id = {node.id: node for node in nodes}
    graph, _ = build_graph(nodes)

    selected_ids: set[str] = set()
    if target_id:
        selected_ids.update(_closure(target_id, nodes_by_id))
    if topic:
        selected_ids.update(_topic_selected(topic, nodes))

    ordered = [
        node_id
        for node_id in topological_sort(graph)
        if node_id in selected_ids
    ]
    missing = sorted(selected_ids - set(ordered))
    ordered.extend(missing)

    return {
        "mode": "admitted+staged" if include_staged else "admitted",
        "target_id": target_id,
        "topic": topic,
        "allowed_inputs": [
            "docs/knowledge/nodes/**/*.md",
            "docs/knowledge/mdblueprint.yml",
            "topics.md catalogs",
            "deterministic graph/index data derived from admitted nodes",
        ] + (["docs/knowledge/staged/**/*.md as non-admitted evidence"] if include_staged else []),
        "forbidden_inputs": FORBIDDEN_INPUTS,
        "answer_contract": {
            "must_cite_node_ids": True,
            "must_report_absent_facts": True,
            "must_mark_non_admitted_evidence": include_staged,
        },
        "nodes": [_node_payload(nodes_by_id[node_id], staged_ids=staged_ids) for node_id in ordered if node_id in nodes_by_id],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build a KB-only mdblueprint context bundle.")
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--target", dest="target_id")
    parser.add_argument("--topic")
    parser.add_argument("--include-staged", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        pack = build_context_pack(
            args.knowledge_root,
            target_id=args.target_id,
            topic=args.topic,
            include_staged=args.include_staged,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(pack, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
