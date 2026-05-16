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
        if g.nodes[dependent_id].kind == "proof-plan":
            continue
        dependent_topic = topic_id_for_node(g.nodes[dependent_id])
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes:
                continue
            if g.nodes[dependency_id].kind == "proof-plan":
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


def _topic_node_counts(g: KnowledgeGraph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for node in g.nodes.values():
        counts[topic_id_for_node(node)] += 1
    return dict(counts)


def _subgraph_node_entry(node: Node) -> dict:
    entry = {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "href": f"{topic_id_for_node(node)}/{node.id.replace('.', '_')}.html",
        "payload": f"node_payloads/{node.id.replace('.', '_')}.json",
    }
    if node.target:
        entry["target"] = node.target
    if node.plan_status:
        entry["plan_status"] = node.plan_status
    return entry


def _boundary_topic_entry(topic_id: str, role: str, node_count: int) -> dict:
    return {
        "id": topic_id,
        "title": titleize_topic(topic_id),
        "href": f"{topic_id}/index.html",
        "role": role,
        "node_count": node_count,
    }


def _keyword_entries(nodes: list[Node]) -> list[dict]:
    counts: Counter[str] = Counter()
    for node in nodes:
        counts.update(node.tags)
    return [
        {
            "id": keyword,
            "title": keyword,
            "href": f"keywords/{keyword}.html",
            "count": count,
        }
        for keyword, count in sorted(counts.items())
    ]


def export_topic_subgraph_json(g: KnowledgeGraph, topic_id: str) -> dict:
    internal_ids = sorted(
        node.id
        for node in g.nodes.values()
        if topic_id_for_node(node) == topic_id
    )
    internal_set = set(internal_ids)
    internal_nodes = [g.nodes[node_id] for node_id in internal_ids]
    topic_counts = _topic_node_counts(g)

    edges = []
    boundary_edge_counts: Counter[tuple[str, str, str, str]] = Counter()
    boundary_roles: dict[str, set[str]] = defaultdict(set)

    for dependent_id in sorted(g.edges):
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes or dependent_id not in g.nodes:
                continue
            dependent_internal = dependent_id in internal_set
            dependency_internal = dependency_id in internal_set
            edge_kind = (
                "proof_plan_uses"
                if g.nodes[dependent_id].kind == "proof-plan" or g.nodes[dependency_id].kind == "proof-plan"
                else "uses"
            )

            if dependent_internal and dependency_internal:
                edges.append({
                    "from": dependency_id,
                    "to": dependent_id,
                    "kind": edge_kind,
                })
                continue

            if dependent_internal and not dependency_internal:
                boundary_topic = topic_id_for_node(g.nodes[dependency_id])
                boundary_roles[boundary_topic].add("dependency")
                boundary_kind = (
                    "boundary_proof_plan_dependency"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependency"
                )
                boundary_edge_counts[(
                    f"topic:{boundary_topic}",
                    dependent_id,
                    boundary_kind,
                    boundary_topic,
                )] += 1
                continue

            if dependency_internal and not dependent_internal:
                boundary_topic = topic_id_for_node(g.nodes[dependent_id])
                boundary_roles[boundary_topic].add("dependent")
                boundary_kind = (
                    "boundary_proof_plan_dependent"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependent"
                )
                boundary_edge_counts[(
                    dependency_id,
                    f"topic:{boundary_topic}",
                    boundary_kind,
                    boundary_topic,
                )] += 1

    boundary_topics = []
    for boundary_topic in sorted(boundary_roles):
        roles = boundary_roles[boundary_topic]
        role = "dependency_and_dependent" if roles == {"dependency", "dependent"} else next(iter(roles))
        boundary_topics.append(_boundary_topic_entry(
            boundary_topic,
            role,
            topic_counts.get(boundary_topic, 0),
        ))

    edge_sort_order = {
        "boundary_dependency": 0,
        "boundary_proof_plan_dependency": 1,
        "boundary_dependent": 2,
        "boundary_proof_plan_dependent": 3,
    }
    boundary_edges = []
    for (source, target, kind, boundary_topic), count in sorted(
        boundary_edge_counts.items(),
        key=lambda item: (edge_sort_order[item[0][2]], item[0][3], item[0][0], item[0][1]),
    ):
        boundary_edges.append({
            "from": source,
            "to": target,
            "kind": kind,
            "topic": boundary_topic,
            "count": count,
        })

    proof_plan_attachments = []
    for plan_id, target_id in sorted(g.proof_plan_targets.items()):
        if plan_id not in g.nodes or target_id not in g.nodes:
            continue
        if plan_id not in internal_set and target_id not in internal_set:
            continue
        plan = g.nodes[plan_id]
        attachment = {
            "from": target_id,
            "to": plan_id,
            "kind": "has_plan",
        }
        if plan.plan_status:
            attachment["plan_status"] = plan.plan_status
        proof_plan_attachments.append(attachment)

    proof_plan_nodes = [node for node in internal_nodes if node.kind == "proof-plan"]
    non_proof_plan_count = len(internal_nodes) - len(proof_plan_nodes)
    selected_proof_plan_count = sum(1 for node in proof_plan_nodes if node.plan_status == "selected")

    return {
        "topic": {
            "id": topic_id,
            "title": titleize_topic(topic_id),
            "href": f"{topic_id}/index.html",
            "node_count": len(internal_ids),
        },
        "counts": {
            "internal_nodes": len(internal_ids),
            "non_proof_plan_nodes": non_proof_plan_count,
            "proof_plan_nodes": len(proof_plan_nodes),
            "selected_proof_plan_nodes": selected_proof_plan_count,
            "boundary_topics": len(boundary_topics),
            "proof_plan_attachments": len(proof_plan_attachments),
            "visible_nodes_without_proof_plans": 1 + len(boundary_topics) + non_proof_plan_count,
            "visible_nodes_with_selected_proof_plans": 1 + len(boundary_topics) + non_proof_plan_count + selected_proof_plan_count,
        },
        "nodes": [_subgraph_node_entry(node) for node in internal_nodes],
        "edges": edges,
        "boundary_topics": boundary_topics,
        "boundary_edges": boundary_edges,
        "keywords": _keyword_entries(internal_nodes),
        "proof_plan_attachments": proof_plan_attachments,
    }


def write_topic_subgraph_jsons(g: KnowledgeGraph, output_dir: Path) -> None:
    topic_ids = sorted({topic_id_for_node(node) for node in g.nodes.values()})
    output_dir.mkdir(parents=True, exist_ok=True)
    for topic_id in topic_ids:
        data = export_topic_subgraph_json(g, topic_id)
        (output_dir / f"{topic_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def export_blueprint_dot(g: KnowledgeGraph) -> str:
    return graph_to_dot(build_blueprint_graph(g))
