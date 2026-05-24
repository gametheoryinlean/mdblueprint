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
    if len(parts) == 1:
        return "misc"
    if len(parts) == 2:
        return parts[0]
    return ".".join(parts[:-1])


def home_topic_for_node(node: Node) -> str:
    """Return the single home/canonical topic for a node.

    Uses ``primary_topic`` when set; falls back to the ID-derived topic.
    """
    if node.primary_topic:
        return node.primary_topic
    return topic_id_for_node(node)


def leaf_topic_ids_for_node(node: Node) -> list[str]:
    """Return all leaf topic IDs this node belongs to (for graph/index views).

    Uses the explicit ``topics`` list when present; falls back to the home
    topic so existing nodes without the field are unaffected.
    """
    if node.topics:
        return list(node.topics)
    return [home_topic_for_node(node)]


def parent_topic_id(topic_id: str) -> str | None:
    parts = topic_id.split(".")
    if len(parts) == 1:
        return None
    return ".".join(parts[:-1])


def topic_depth(topic_id: str) -> int:
    return len(topic_id.split("."))


def topic_slug(topic_id: str) -> str:
    return topic_id.replace(".", "-")


def topic_path(topic_id: str) -> str:
    return topic_id.replace(".", "/")


def topic_prefixes(topic_id: str) -> list[str]:
    parts = topic_id.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts) + 1)]


def root_topic_id(topic_id: str) -> str:
    return topic_id.split(".", 1)[0]


def child_topic_id(parent_id: str, descendant_id: str) -> str | None:
    if descendant_id == parent_id:
        return None
    prefix = f"{parent_id}."
    if not descendant_id.startswith(prefix):
        return None
    remainder = descendant_id[len(prefix):]
    child_slug = remainder.split(".", 1)[0]
    return f"{parent_id}.{child_slug}"


def titleize_topic(topic_id: str) -> str:
    return topic_id.replace("_", " ").replace("-", " ").title()


def _empty_topic_data(topic_id: str) -> dict:
    return {
        "direct_nodes": [],
        "all_nodes": [],
        "children": set(),
        "parent": parent_topic_id(topic_id),
    }


def _topic_hierarchy_data(g: KnowledgeGraph) -> dict[str, dict]:
    topic_data: dict[str, dict] = {}
    for node in g.nodes.values():
        for leaf_topic in leaf_topic_ids_for_node(node):
            for topic_id in topic_prefixes(leaf_topic):
                topic_data.setdefault(topic_id, _empty_topic_data(topic_id))
                if node not in topic_data[topic_id]["all_nodes"]:
                    topic_data[topic_id]["all_nodes"].append(node)
            if node not in topic_data[leaf_topic]["direct_nodes"]:
                topic_data[leaf_topic]["direct_nodes"].append(node)

    for topic_id in list(topic_data):
        parent = topic_data[topic_id]["parent"]
        if parent is not None:
            topic_data.setdefault(parent, _empty_topic_data(parent))
            topic_data[parent]["children"].add(topic_id)

    return topic_data


def _topic_entry(topic_id: str, data: dict) -> dict:
    nodes = data["all_nodes"]
    kind_counts = Counter(node.kind for node in nodes)
    status_counts = Counter(node.status for node in nodes)
    children = sorted(data["children"])
    return {
        "id": topic_id,
        "title": titleize_topic(topic_id),
        "depth": topic_depth(topic_id),
        "parent": data["parent"],
        "node_count": len(nodes),
        "direct_node_count": len(data["direct_nodes"]),
        "kind_counts": dict(sorted(kind_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "href": f"{topic_path(topic_id)}/index.html",
        "children": children,
    }


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
        if node.primary_topic:
            entry["primary_topic"] = node.primary_topic
        if node.topics:
            entry["topics"] = node.topics
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
            edges.append({"from": dep, "to": nid})

    return {"nodes": nodes, "edges": edges}


def write_graph_json(g: KnowledgeGraph, output: Path) -> None:
    data = export_graph_json(g)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def export_topic_overview_json(g: KnowledgeGraph) -> dict:
    topic_data = _topic_hierarchy_data(g)
    root_ids = sorted(topic_id for topic_id, data in topic_data.items() if data["parent"] is None)
    topics = []
    for topic_id in root_ids:
        topics.append(_topic_entry(topic_id, topic_data[topic_id]))

    # Topic-overview edges are derived from each node's single canonical
    # (home) topic, not from every entry in its `topics:` field. The
    # `topics:` field is a discoverability tag — adding a secondary tag
    # for navigation must not fabricate a cross-topic dependency edge.
    edge_counts: Counter[tuple[str, str]] = Counter()
    for dependent_id in sorted(g.edges):
        if g.nodes[dependent_id].kind == "proof-plan":
            continue
        dependent_topic = root_topic_id(home_topic_for_node(g.nodes[dependent_id]))
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes:
                continue
            if g.nodes[dependency_id].kind == "proof-plan":
                continue
            dependency_topic = root_topic_id(home_topic_for_node(g.nodes[dependency_id]))
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


def export_topic_hierarchy_json(g: KnowledgeGraph) -> dict:
    topic_data = _topic_hierarchy_data(g)
    roots = sorted(tid for tid, d in topic_data.items() if d["parent"] is None)

    return {
        "roots": [_topic_entry(r, topic_data[r]) for r in roots],
        "topics": {tid: _topic_entry(tid, topic_data[tid]) for tid in sorted(topic_data)},
    }


def write_topic_overview_json(g: KnowledgeGraph, output: Path) -> None:
    data = export_topic_overview_json(g)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_topic_hierarchy_json(g: KnowledgeGraph, output: Path) -> None:
    data = export_topic_hierarchy_json(g)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _topic_node_counts(g: KnowledgeGraph) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for node in g.nodes.values():
        seen: set[str] = set()
        for leaf_topic in leaf_topic_ids_for_node(node):
            for topic_id in topic_prefixes(leaf_topic):
                if topic_id not in seen:
                    counts[topic_id] += 1
                    seen.add(topic_id)
    return dict(counts)


def _subgraph_node_entry(node: Node) -> dict:
    entry = {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "href": f"{topic_path(home_topic_for_node(node))}/{node.id.replace('.', '_')}.html",
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
        "href": f"{topic_path(topic_id)}/index.html",
        "role": role,
        "node_count": node_count,
    }


def _child_topic_edges(g: KnowledgeGraph, topic_id: str) -> list[dict]:
    # Each node contributes exactly one canonical endpoint — its home topic —
    # when participating in the child-topic edge set. Secondary `topics:[]`
    # entries are discoverability tags and must not fabricate phantom child
    # topic edges. See #131 / #135 for the rationale.
    edge_counts: Counter[tuple[str, str]] = Counter()
    for dependent_id in sorted(g.edges):
        if dependent_id not in g.nodes or g.nodes[dependent_id].kind == "proof-plan":
            continue
        dependent_home = home_topic_for_node(g.nodes[dependent_id])
        dependent_child = child_topic_id(topic_id, dependent_home)
        if dependent_child is None:
            continue
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes or g.nodes[dependency_id].kind == "proof-plan":
                continue
            dependency_home = home_topic_for_node(g.nodes[dependency_id])
            dependency_child = child_topic_id(topic_id, dependency_home)
            if dependency_child is None or dependency_child == dependent_child:
                continue
            edge_counts[(dependency_child, dependent_child)] += 1

    return [
        {
            "from": f"topic:{source}",
            "to": f"topic:{target}",
            "kind": "topic_dependency",
            "count": count,
        }
        for (source, target), count in sorted(edge_counts.items())
    ]


def _topic_layer_boundary(g: KnowledgeGraph, topic_id: str, topic_counts: dict[str, int]) -> tuple[list[dict], list[dict]]:
    # Each node contributes exactly one canonical endpoint — its home topic —
    # when participating in the boundary set. Secondary `topics:[]` entries
    # are discoverability tags and must not fabricate phantom boundary topics
    # under the same root. See #131 / #135.
    boundary_roles: dict[str, set[str]] = defaultdict(set)
    edge_counts: Counter[tuple[str, str, str, str]] = Counter()

    def inside_current(node_topic: str) -> bool:
        return node_topic == topic_id or node_topic.startswith(f"{topic_id}.")

    for dependent_id in sorted(g.edges):
        if dependent_id not in g.nodes or g.nodes[dependent_id].kind == "proof-plan":
            continue
        dependent_home = home_topic_for_node(g.nodes[dependent_id])
        dependent_inside = inside_current(dependent_home)
        dependent_child = (
            child_topic_id(topic_id, dependent_home) if dependent_inside else None
        )

        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes or g.nodes[dependency_id].kind == "proof-plan":
                continue
            dependency_home = home_topic_for_node(g.nodes[dependency_id])
            dependency_inside = inside_current(dependency_home)
            dependency_child = (
                child_topic_id(topic_id, dependency_home) if dependency_inside else None
            )

            if dependent_child is not None and not dependency_inside:
                boundary_roles[dependency_home].add("dependency")
                edge_counts[(
                    f"topic:{dependency_home}",
                    f"topic:{dependent_child}",
                    "boundary_dependency",
                    dependency_home,
                )] += 1
            if dependency_child is not None and not dependent_inside:
                boundary_roles[dependent_home].add("dependent")
                edge_counts[(
                    f"topic:{dependency_child}",
                    f"topic:{dependent_home}",
                    "boundary_dependent",
                    dependent_home,
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
        "boundary_dependent": 1,
    }
    boundary_edges = [
        {
            "from": source,
            "to": target,
            "kind": kind,
            "topic": boundary_topic,
            "count": count,
        }
        for (source, target, kind, boundary_topic), count in sorted(
            edge_counts.items(),
            key=lambda item: (edge_sort_order[item[0][2]], item[0][3], item[0][0], item[0][1]),
        )
    ]
    return boundary_topics, boundary_edges


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


def export_topic_subgraph_json(
    g: KnowledgeGraph,
    topic_id: str,
    *,
    graph_config: "GraphDisplayConfig | None" = None,
) -> dict:
    from tools.knowledge.config import GraphDisplayConfig as _GraphCfg

    cfg = graph_config if graph_config is not None else _GraphCfg(
        max_visible_nodes=120,
        max_expand_nodes=80,
        proof_plans="selected-only",
    )

    topic_data = _topic_hierarchy_data(g)
    current_topic_data = topic_data.get(topic_id, _empty_topic_data(topic_id))
    child_ids = sorted(current_topic_data["children"])
    internal_ids = sorted(
        node.id
        for node in g.nodes.values()
        if topic_id in leaf_topic_ids_for_node(node)
    )
    internal_set = set(internal_ids)
    internal_nodes = [g.nodes[node_id] for node_id in internal_ids]
    topic_counts = _topic_node_counts(g)

    # `internal_set` drives what nodes the page lists by virtue of their
    # explicit `topics:[]` tag. `family_set` is the broader universe of
    # "nodes inside this topic's hierarchical scope" — current topic plus
    # every descendant by home topic. See #136.
    def _in_family(node: Node) -> bool:
        h = home_topic_for_node(node)
        return h == topic_id or h.startswith(f"{topic_id}.")

    family_set = {node.id for node in g.nodes.values() if _in_family(node)}

    # Adaptive inlining (#139): small child topics fold their entire subtree
    # into this page's flat node list instead of being shown as a single box,
    # subject to two knobs:
    #   - graph.inline_child_max_size — per-child eligibility threshold
    #   - graph.max_page_total — hard cap on visible flat nodes per page
    # `_count_family_nodes(c)` returns the size of the subtree rooted at c.
    child_subtree_sizes: dict[str, int] = {
        child: sum(
            1 for node in g.nodes.values()
            if home_topic_for_node(node) == child
            or home_topic_for_node(node).startswith(f"{child}.")
        )
        for child in child_ids
    }
    inlined_children: set[str] = set()
    used_budget = len(internal_ids)
    candidates = sorted(
        (
            (child, size)
            for child, size in child_subtree_sizes.items()
            if 0 < size <= cfg.inline_child_max_size
        ),
        key=lambda item: (item[1], item[0]),
    )
    for child, size in candidates:
        if used_budget + size <= cfg.max_page_total:
            inlined_children.add(child)
            used_budget += size

    # Nodes pulled onto this page by inlining their parent child topic.
    inlined_node_ids: set[str] = set()
    for child in inlined_children:
        for node in g.nodes.values():
            h = home_topic_for_node(node)
            if h == child or h.startswith(f"{child}."):
                inlined_node_ids.add(node.id)
    inlined_node_ids -= internal_set  # internal nodes are already represented

    # Effective page set governs edge classification: any flat node on the page
    # — whether tagged-into-topic or pulled-in-by-inlining — counts as
    # "internal" for the purposes of routing edges through boundary boxes vs.
    # plain edges.
    effective_internal_set = internal_set | inlined_node_ids

    # Render-ready node list: internal nodes plus the pulled-in inlined nodes.
    page_nodes = list(internal_nodes) + [
        g.nodes[nid] for nid in sorted(inlined_node_ids)
    ]

    edges = []
    boundary_edge_counts: Counter[tuple[str, str, str, str]] = Counter()
    boundary_roles: dict[str, set[str]] = defaultdict(set)

    for dependent_id in sorted(g.edges):
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes or dependent_id not in g.nodes:
                continue
            dependent_in_family = dependent_id in family_set
            dependency_in_family = dependency_id in family_set
            dependent_in_internal = dependent_id in effective_internal_set
            dependency_in_internal = dependency_id in effective_internal_set
            edge_kind = (
                "proof_plan_uses"
                if g.nodes[dependent_id].kind == "proof-plan" or g.nodes[dependency_id].kind == "proof-plan"
                else "uses"
            )

            # Both endpoints rendered as page items → flat internal edge.
            if dependent_in_internal and dependency_in_internal:
                edges.append({
                    "from": dependency_id,
                    "to": dependent_id,
                    "kind": edge_kind,
                })
                continue

            # Both endpoints inside the topic family but at least one is a
            # descendant not listed as a page item (the descendant gets shown
            # as a child_topic_node box). Aggregate per the child topic. Pure
            # descendant↔descendant cases are also covered by _child_topic_edges;
            # we still emit here so child_topic↔internal_node edges render.
            if dependent_in_family and dependency_in_family:
                if not dependent_in_internal:
                    # Dependent lives in a descendant child topic; arrow ends
                    # at that child_topic_node box.
                    dep_child = child_topic_id(topic_id, home_topic_for_node(g.nodes[dependent_id]))
                    if dep_child is not None and dependency_in_internal:
                        boundary_edge_counts[(
                            dependency_id,
                            f"topic:{dep_child}",
                            "boundary_dependent" if edge_kind == "uses" else "boundary_proof_plan_dependent",
                            dep_child,
                        )] += 1
                if not dependency_in_internal:
                    # Dependency lives in a descendant; arrow starts from that
                    # child_topic_node box.
                    dep_child = child_topic_id(topic_id, home_topic_for_node(g.nodes[dependency_id]))
                    if dep_child is not None and dependent_in_internal:
                        boundary_edge_counts[(
                            f"topic:{dep_child}",
                            dependent_id,
                            "boundary_dependency" if edge_kind == "uses" else "boundary_proof_plan_dependency",
                            dep_child,
                        )] += 1
                # Pure descendant↔descendant edges are already aggregated by
                # _child_topic_edges; no extra emission here.
                continue

            # True boundary edge: exactly one endpoint outside the family.
            if dependent_in_family and not dependency_in_family:
                boundary_topic = home_topic_for_node(g.nodes[dependency_id])
                boundary_roles[boundary_topic].add("dependency")
                boundary_kind = (
                    "boundary_proof_plan_dependency"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependency"
                )
                boundary_edge_counts[(
                    f"topic:{boundary_topic}",
                    dependent_id if dependent_in_internal
                    else f"topic:{child_topic_id(topic_id, home_topic_for_node(g.nodes[dependent_id]))}",
                    boundary_kind,
                    boundary_topic,
                )] += 1
                continue

            if dependency_in_family and not dependent_in_family:
                boundary_topic = home_topic_for_node(g.nodes[dependent_id])
                boundary_roles[boundary_topic].add("dependent")
                boundary_kind = (
                    "boundary_proof_plan_dependent"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependent"
                )
                boundary_edge_counts[(
                    dependency_id if dependency_in_internal
                    else f"topic:{child_topic_id(topic_id, home_topic_for_node(g.nodes[dependency_id]))}",
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
        if plan_id not in effective_internal_set and target_id not in effective_internal_set:
            continue
        plan = g.nodes[plan_id]
        # has_plan edges follow the same orientation as every other graph
        # edge in mdblueprint: dependency -> dependent. The proof-plan is
        # the prerequisite that establishes the target theorem, so the
        # plan node is the source and the target theorem is the sink.
        attachment = {
            "from": plan_id,
            "to": target_id,
            "kind": "has_plan",
        }
        if plan.plan_status:
            attachment["plan_status"] = plan.plan_status
        proof_plan_attachments.append(attachment)

    proof_plan_nodes = [node for node in page_nodes if node.kind == "proof-plan"]
    non_proof_plan_count = len(page_nodes) - len(proof_plan_nodes)
    selected_proof_plan_count = sum(1 for node in proof_plan_nodes if node.plan_status == "selected")

    # Inlined children no longer get a separate box on the page — their
    # contents now appear directly in `nodes`. Drop them from the child topic
    # list and from `_child_topic_edges` (whose endpoints become flat edges
    # already accounted for above).
    visible_child_ids = [c for c in child_ids if c not in inlined_children]
    child_topic_nodes = [
        _topic_entry(child_id, topic_data[child_id])
        for child_id in visible_child_ids
    ]
    raw_child_topic_edges = _child_topic_edges(g, topic_id)
    child_topic_edges = [
        edge
        for edge in raw_child_topic_edges
        if edge["from"].removeprefix("topic:") not in inlined_children
        and edge["to"].removeprefix("topic:") not in inlined_children
    ]
    child_boundary_topics, child_boundary_edges = _topic_layer_boundary(g, topic_id, topic_counts)

    return {
        "topic": {
            "id": topic_id,
            "title": titleize_topic(topic_id),
            "href": f"{topic_path(topic_id)}/index.html",
            "parent": parent_topic_id(topic_id),
            "node_count": len(internal_ids),
            "descendant_node_count": len(current_topic_data["all_nodes"]),
        },
        "counts": {
            "internal_nodes": len(internal_ids),
            "inlined_nodes": len(inlined_node_ids),
            "descendant_nodes": len(current_topic_data["all_nodes"]),
            "child_topics": len(child_topic_nodes),
            "inlined_child_topics": len(inlined_children),
            "non_proof_plan_nodes": non_proof_plan_count,
            "proof_plan_nodes": len(proof_plan_nodes),
            "selected_proof_plan_nodes": selected_proof_plan_count,
            "boundary_topics": len(boundary_topics),
            "proof_plan_attachments": len(proof_plan_attachments),
            "visible_nodes_without_proof_plans": 1 + len(boundary_topics) + non_proof_plan_count,
            "visible_nodes_with_selected_proof_plans": 1 + len(boundary_topics) + non_proof_plan_count + selected_proof_plan_count,
        },
        "nodes": [_subgraph_node_entry(node) for node in page_nodes],
        "edges": edges,
        "boundary_topics": boundary_topics,
        "boundary_edges": boundary_edges,
        "keywords": _keyword_entries(page_nodes),
        "proof_plan_attachments": proof_plan_attachments,
        "child_topics": visible_child_ids,
        "child_topic_nodes": child_topic_nodes,
        "child_topic_edges": child_topic_edges,
        "child_boundary_topics": child_boundary_topics,
        "child_boundary_edges": child_boundary_edges,
        "inlined_child_topics": sorted(inlined_children),
    }


def write_topic_subgraph_jsons(
    g: KnowledgeGraph,
    output_dir: Path,
    *,
    graph_config: "GraphDisplayConfig | None" = None,
) -> None:
    topic_ids = sorted(_topic_hierarchy_data(g))
    output_dir.mkdir(parents=True, exist_ok=True)
    for topic_id in topic_ids:
        data = export_topic_subgraph_json(g, topic_id, graph_config=graph_config)
        (output_dir / f"{topic_id}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def export_blueprint_dot(g: KnowledgeGraph) -> str:
    return graph_to_dot(build_blueprint_graph(g))
