"""Export knowledge graph to graph.json."""
from __future__ import annotations

import json
from pathlib import Path

from tools.knowledge.graph import KnowledgeGraph


def export_graph_json(g: KnowledgeGraph) -> dict:
    nodes = []
    for nid in sorted(g.nodes):
        node = g.nodes[nid]
        entry: dict = {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
        }
        if node.tags:
            entry["tags"] = node.tags
        if node.lean:
            entry["lean_declarations"] = node.lean.declarations
        if node.file_path:
            entry["topic"] = str(node.file_path.parent.name)
        deps = g.edges.get(nid, [])
        if deps:
            entry["uses"] = sorted(deps)
        dependents = g.reverse_edges.get(nid, [])
        if dependents:
            entry["used_by"] = sorted(dependents)
        nodes.append(entry)

    edges = []
    for nid in sorted(g.edges):
        for dep in sorted(g.edges[nid]):
            edges.append({"from": nid, "to": dep})

    return {"nodes": nodes, "edges": edges}


def write_graph_json(g: KnowledgeGraph, output: Path) -> None:
    data = export_graph_json(g)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
