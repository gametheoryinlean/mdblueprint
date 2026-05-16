"""Export knowledge graph to graph.json."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.models import Node


def topic_id_for_node(node: Node) -> str:
    parts = node.id.split(".")
    return parts[0] if len(parts) > 1 else "misc"


def titleize_topic(topic_id: str) -> str:
    return topic_id.replace("_", " ").replace("-", " ").title()


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
        if node.target:
            entry["target"] = node.target
        if node.plan_status:
            entry["plan_status"] = node.plan_status
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


def export_topic_overview_json(g: KnowledgeGraph) -> dict:
    topic_nodes: dict[str, list[Node]] = defaultdict(list)
    for node in g.nodes.values():
        topic_nodes[topic_id_for_node(node)].append(node)

    topics = []
    for topic_id in sorted(topic_nodes):
        nodes = sorted(topic_nodes[topic_id], key=lambda node: node.id)
        kind_counts = Counter(node.kind for node in nodes)
        status_counts = Counter(node.status for node in nodes)
        topics.append({
            "id": topic_id,
            "title": titleize_topic(topic_id),
            "node_count": len(nodes),
            "kind_counts": dict(sorted(kind_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "href": f"{topic_id}/index.html",
        })

    edge_counts: Counter[tuple[str, str]] = Counter()
    for dependent_id in sorted(g.edges):
        dependent_topic = topic_id_for_node(g.nodes[dependent_id])
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes:
                continue
            dependency_topic = topic_id_for_node(g.nodes[dependency_id])
            if dependency_topic == dependent_topic:
                continue
            edge_counts[(dependency_topic, dependent_topic)] += 1

    edges = [
        {
            "from": source,
            "to": target,
            "count": count,
        }
        for (source, target), count in sorted(edge_counts.items())
    ]
    return {"topics": topics, "edges": edges}


def write_topic_overview_json(g: KnowledgeGraph, output: Path) -> None:
    data = export_topic_overview_json(g)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export_blueprint_dot(g: KnowledgeGraph) -> str:
    return graph_to_dot(build_blueprint_graph(g))
