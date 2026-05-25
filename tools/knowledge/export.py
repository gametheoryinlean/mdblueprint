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


def memberships(node: Node) -> list[str]:
    """Return the list of topics this node logically belongs to for page placement.

    When ``topics:[]`` is non-empty, use it exactly — it represents explicit
    multi-topic membership chosen by the author. Otherwise fall back to the
    full chain of ID-derived prefixes of the node's own ID (e.g.
    ``foo.bar.baz`` → ``["foo", "foo.bar", "foo.bar.baz"]``).

    ``primary_topic`` is URL/file-path only and intentionally excluded here.
    """
    if node.topics:
        return list(node.topics)
    return topic_prefixes(node.id)


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


def _anchor_child(topic_id: str, node: Node) -> str | None:
    """Return the immediate child of ``topic_id`` that anchors ``node``,
    looking through ``memberships`` rather than ``home_topic``.

    If the node has any membership that is a strict descendant of ``topic_id``,
    return the immediate child of ``topic_id`` that leads to it. If all
    memberships are exactly ``topic_id`` (direct membership), return ``None``
    (the node is directly tagged to this page).

    When a node has both a direct ``topic_id`` membership AND a subtopic
    membership (e.g. ``topics: [core, core.subA]``), the subtopic wins — it
    provides the more specific anchor for subdivision decisions.
    """
    prefix = f"{topic_id}."
    child_anchor: str | None = None
    for m in memberships(node):
        if m.startswith(prefix):
            remainder = m[len(prefix):]
            child_slug = remainder.split(".", 1)[0]
            candidate = f"{topic_id}.{child_slug}"
            # Keep the first (most-specific in iteration order) subtopic child.
            if child_anchor is None:
                child_anchor = candidate
    return child_anchor


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
    topic_counts = _topic_node_counts(g)

    # Step 1: Collect P = all nodes whose memberships include T or a subtopic of T.
    # memberships() drives every size / anchor decision; primary_topic is URL-only.
    def _in_page_scope(node: Node) -> bool:
        t_prefix = f"{topic_id}."
        for m in memberships(node):
            if m == topic_id or m.startswith(t_prefix):
                return True
        return False

    page_scope_ids = sorted(node.id for node in g.nodes.values() if _in_page_scope(node))
    page_scope_set = set(page_scope_ids)

    # For counting and metadata we also need the old-style "internal" (direct
    # topic-tagged) count used in `counts.internal_nodes`.
    internal_ids_for_counts = sorted(
        node.id
        for node in g.nodes.values()
        if topic_id in leaf_topic_ids_for_node(node)
    )

    # Step 2 / Step 3: Decide which nodes render flat and which fold into boxes.
    # Default is fully flat. We only fold when |page_scope_set| > max_page_total.

    # Per-child subtree sizes via memberships (not home_topic).
    # anchor_child_for_node maps node.id -> immediate child of topic_id (or None).
    anchor_child_for_node: dict[str, str | None] = {}
    for node in g.nodes.values():
        if node.id in page_scope_set:
            anchor_child_for_node[node.id] = _anchor_child(topic_id, node)

    # Nodes directly tagged to topic_id (anchor = None) are always flat.
    directly_tagged_ids = {
        nid for nid, anchor in anchor_child_for_node.items() if anchor is None
    }
    # Group the rest by their anchor child.
    child_members: dict[str, set[str]] = defaultdict(set)
    for nid, anchor in anchor_child_for_node.items():
        if anchor is not None:
            child_members[anchor].add(nid)

    if len(page_scope_set) <= cfg.max_page_total:
        # Under cap — render everything flat, no child boxes.
        flat_set = page_scope_set
        folded_children: dict[str, set[str]] = {}
    else:
        # Over cap — greedy-fold the largest child groups until under cap.
        # Start with all in flat_set; move the biggest children into boxes.
        flat_set = set(page_scope_set)
        folded_children = {}
        # Sort candidates by descending size (then id for determinism).
        fold_candidates = sorted(
            child_members.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
        for child, members in fold_candidates:
            if len(flat_set) <= cfg.max_page_total:
                break
            flat_set -= members
            folded_children[child] = members

    # Nodes explicitly inlined (were in child_members, now in flat_set).
    # For the `inlined_child_topics` field, these are children whose members
    # ended up flat even though they have a subtopic anchor.
    inlined_children: set[str] = {
        child for child, members in child_members.items()
        if child not in folded_children
        and members  # non-empty child group
    }

    # Legacy compat: separate "internal_set" (direct topic-tagged) vs
    # nodes pulled in because their subtopic was inlined.
    internal_set = {
        nid for nid in flat_set
        if anchor_child_for_node.get(nid) is None
    }
    inlined_node_ids = flat_set - internal_set

    # Render-ready node list (sorted for determinism).
    page_nodes = [g.nodes[nid] for nid in sorted(flat_set)]

    # The family set for external-boundary detection: home_topic still used here
    # because boundary topics for the cross-topic view are URL-keyed.
    def _in_family_home(node: Node) -> bool:
        h = home_topic_for_node(node)
        return h == topic_id or h.startswith(f"{topic_id}.")

    family_set = {node.id for node in g.nodes.values() if _in_family_home(node)}
    # Also include memberships-based scope for internal edge routing.
    family_set |= page_scope_set

    # Edge emission.
    edges = []
    boundary_edge_counts: Counter[tuple[str, str, str, str]] = Counter()
    boundary_roles: dict[str, set[str]] = defaultdict(set)

    # topic_dep_edge_counts aggregates box→box edges for folded children.
    topic_dep_counts: Counter[tuple[str, str]] = Counter()

    for dependent_id in sorted(g.edges):
        for dependency_id in sorted(g.edges[dependent_id]):
            if dependency_id not in g.nodes or dependent_id not in g.nodes:
                continue

            dep_node = g.nodes[dependent_id]
            dep_cy_node = g.nodes[dependency_id]

            dependent_flat = dependent_id in flat_set
            dependency_flat = dependency_id in flat_set
            dependent_in_scope = dependent_id in page_scope_set
            dependency_in_scope = dependency_id in page_scope_set

            edge_kind = (
                "proof_plan_uses"
                if dep_node.kind == "proof-plan" or dep_cy_node.kind == "proof-plan"
                else "uses"
            )

            # Both flat → flat internal edge.
            if dependent_flat and dependency_flat:
                edges.append({
                    "from": dependency_id,
                    "to": dependent_id,
                    "kind": edge_kind,
                })
                continue

            # Both in page scope (flat or folded).
            if dependent_in_scope and dependency_in_scope:
                dep_box = anchor_child_for_node.get(dependent_id)
                decy_box = anchor_child_for_node.get(dependency_id)
                dep_folded = dep_box is not None and dep_box in folded_children
                decy_folded = decy_box is not None and decy_box in folded_children

                if dep_folded and decy_folded:
                    if dep_box != decy_box:
                        # Cross-box edge — aggregate as topic_dependency.
                        topic_dep_counts[(decy_box, dep_box)] += 1  # type: ignore[index]
                    # Same-box → suppress.
                    continue

                if dep_folded and dependency_flat:
                    # Dependent in a folded box; dependency is flat.
                    boundary_edge_counts[(
                        dependency_id,
                        f"topic:{dep_box}",
                        "boundary_dependent" if edge_kind == "uses" else "boundary_proof_plan_dependent",
                        dep_box,  # type: ignore[arg-type]
                    )] += 1
                    continue

                if decy_folded and dependent_flat:
                    # Dependency in a folded box; dependent is flat.
                    boundary_edge_counts[(
                        f"topic:{decy_box}",
                        dependent_id,
                        "boundary_dependency" if edge_kind == "uses" else "boundary_proof_plan_dependency",
                        decy_box,  # type: ignore[arg-type]
                    )] += 1
                    continue

                # Both flat (already handled above) or other combo — skip.
                continue

            # True boundary edge: exactly one endpoint outside page scope.
            if dependent_in_scope and not dependency_in_scope:
                boundary_topic = home_topic_for_node(dep_cy_node)
                boundary_roles[boundary_topic].add("dependency")
                boundary_kind = (
                    "boundary_proof_plan_dependency"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependency"
                )
                dep_box = anchor_child_for_node.get(dependent_id)
                dep_folded = dep_box is not None and dep_box in folded_children
                boundary_edge_counts[(
                    f"topic:{boundary_topic}",
                    dependent_id if not dep_folded else f"topic:{dep_box}",
                    boundary_kind,
                    boundary_topic,
                )] += 1
                continue

            if dependency_in_scope and not dependent_in_scope:
                boundary_topic = home_topic_for_node(dep_node)
                boundary_roles[boundary_topic].add("dependent")
                boundary_kind = (
                    "boundary_proof_plan_dependent"
                    if edge_kind == "proof_plan_uses"
                    else "boundary_dependent"
                )
                decy_box = anchor_child_for_node.get(dependency_id)
                decy_folded = decy_box is not None and decy_box in folded_children
                boundary_edge_counts[(
                    dependency_id if not decy_folded else f"topic:{decy_box}",
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
        if plan_id not in flat_set and target_id not in flat_set:
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

    # Build visible child topic nodes — only folded children with ≥1 member.
    # topic_data may not have entries for all child anchors if they only exist
    # by memberships() (not home_topic), so we build a synthetic entry when needed.
    visible_child_ids = sorted(folded_children.keys())
    child_topic_nodes = []
    for child_id in visible_child_ids:
        member_count = len(folded_children[child_id])
        if member_count == 0:
            continue  # Never render empty boxes.
        if child_id in topic_data:
            child_topic_nodes.append(_topic_entry(child_id, topic_data[child_id]))
        else:
            # Synthetic entry for a child that only exists via memberships.
            synthetic = _empty_topic_data(child_id)
            synthetic["all_nodes"] = [g.nodes[nid] for nid in folded_children[child_id] if nid in g.nodes]
            synthetic["direct_nodes"] = synthetic["all_nodes"]
            child_topic_nodes.append(_topic_entry(child_id, synthetic))

    # topic_dependency edges between folded boxes.
    child_topic_edges = [
        {
            "from": f"topic:{source}",
            "to": f"topic:{target}",
            "kind": "topic_dependency",
            "count": count,
        }
        for (source, target), count in sorted(topic_dep_counts.items())
    ]

    # child_boundary edges (the per-layer boundary, used by the child-topic
    # overview view). Still derived via home_topic for the cross-topic surface.
    child_boundary_topics, child_boundary_edges = _topic_layer_boundary(g, topic_id, topic_counts)

    return {
        "topic": {
            "id": topic_id,
            "title": titleize_topic(topic_id),
            "href": f"{topic_path(topic_id)}/index.html",
            "parent": parent_topic_id(topic_id),
            "node_count": len(internal_ids_for_counts),
            "descendant_node_count": len(current_topic_data["all_nodes"]),
        },
        "counts": {
            "internal_nodes": len(internal_ids_for_counts),
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
