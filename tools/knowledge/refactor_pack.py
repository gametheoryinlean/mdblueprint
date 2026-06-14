"""Build bounded refactor evidence bundles for graph-refactor agents."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

from tools.knowledge.config import load_project_config
from tools.knowledge.export import home_topic_for_node, leaf_topic_ids_for_node
from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.lint import Linter, _default_detectors
from tools.knowledge.models import Node
from tools.knowledge.node_refs import NODE_REF_RE
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic


ALLOWED_INPUTS = [
    "docs/knowledge/nodes/**/*.md",
    "docs/knowledge/mdblueprint.yml",
    "topics.md catalogs",
    "deterministic graph/index data derived from loaded nodes",
]

FORBIDDEN_INPUTS = [
    "source artifacts",
    "internet",
    "uncited model memory",
    "generated graph/site artifacts as source of truth",
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


def _bounded_walk(
    graph: KnowledgeGraph,
    start_id: str,
    *,
    direction: str,
    max_depth: int,
) -> dict[str, int]:
    """Return reachable ids and minimum distance from ``start_id``.

    ``direction="ancestors"`` follows ordinary ``uses`` edges toward
    prerequisites. ``direction="descendants"`` follows reverse edges toward
    nodes that depend on the start node.
    """
    if max_depth <= 0 or start_id not in graph.nodes:
        return {}
    adjacency = graph.edges if direction == "ancestors" else graph.reverse_edges
    distances: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque((nid, 1) for nid in sorted(adjacency.get(start_id, [])))
    while queue:
        node_id, distance = queue.popleft()
        if node_id in distances and distances[node_id] <= distance:
            continue
        if distance > max_depth:
            continue
        distances[node_id] = distance
        if distance == max_depth:
            continue
        for next_id in sorted(adjacency.get(node_id, [])):
            queue.append((next_id, distance + 1))
    return distances


def _topic_matches(node: Node, topic: str) -> bool:
    return any(
        member == topic or member.startswith(topic + ".")
        for member in leaf_topic_ids_for_node(node)
    )


def _topic_selected(nodes: list[Node], topic: str) -> set[str]:
    return {node.id for node in nodes if _topic_matches(node, topic)}


def _body_refs(node: Node, all_ids: set[str]) -> dict[str, Any]:
    refs: list[dict[str, Any]] = []
    missing_from_uses: list[str] = []
    seen_missing: set[str] = set()
    uses = set(node.uses or [])
    for match in NODE_REF_RE.finditer(node.body or ""):
        ref_id = match.group(1)
        known = ref_id in all_ids
        refs.append({
            "target_id": ref_id,
            "known": known,
            "in_uses": ref_id in uses,
        })
        if known and ref_id != node.id and ref_id not in uses and ref_id not in seen_missing:
            seen_missing.add(ref_id)
            missing_from_uses.append(ref_id)
    return {
        "refs": refs,
        "missing_from_uses": missing_from_uses,
    }


def _node_payload(
    node: Node,
    graph: KnowledgeGraph,
    *,
    staged_ids: set[str],
    all_ids: set[str],
) -> dict[str, Any]:
    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "evidence": "non-admitted" if node.id in staged_ids else "admitted",
        "home_topic": home_topic_for_node(node),
        "topics": leaf_topic_ids_for_node(node),
        "uses": list(node.uses or []),
        "used_by": sorted(graph.reverse_edges.get(node.id, [])),
        "file_path": str(node.file_path) if node.file_path else None,
        "body_refs": _body_refs(node, all_ids),
        "body": node.body,
    }


def _diagnostic_payload(diag: Diagnostic) -> dict[str, Any]:
    return {
        "level": diag.level,
        "node_id": diag.node_id,
        "message": diag.message,
        "file_path": str(diag.file_path) if diag.file_path is not None else None,
        "code": diag.code,
        "related": list(diag.related),
    }


def _run_lint(root: Path) -> list[Diagnostic]:
    config = load_project_config(root)
    linter = Linter(
        detectors=_default_detectors(config.lint),
        llm=None,
    )
    return linter.run(root)


def _relevant_lint_findings(
    diags: list[Diagnostic],
    *,
    selected_ids: set[str],
    loaded_ids: set[str],
    topic_ids: set[str],
    include_staged: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for diag in diags:
        related = set(diag.related)
        node_id = diag.node_id
        if not include_staged and node_id and node_id not in loaded_ids:
            continue
        relevant = False
        if node_id in selected_ids or related.intersection(selected_ids):
            relevant = True
        elif node_id in topic_ids or related.intersection(topic_ids):
            relevant = True
        elif not node_id and topic_ids:
            relevant = True
        if relevant:
            out.append(_diagnostic_payload(diag))
    return out


def _ordered_ids(
    *,
    target_id: str | None,
    topic: str | None,
    topic_ids: set[str],
    direct_deps: list[str],
    direct_dependents: list[str],
    ancestors: dict[str, int],
    descendants: dict[str, int],
    siblings: list[str],
    max_nodes: int,
) -> tuple[list[str], bool]:
    candidates: list[str] = []
    if target_id:
        candidates.append(target_id)
    if topic:
        candidates.extend(sorted(topic_ids))
    candidates.extend(direct_deps)
    candidates.extend(direct_dependents)
    candidates.extend(nid for nid, _ in sorted(ancestors.items(), key=lambda item: (item[1], item[0])))
    candidates.extend(nid for nid, _ in sorted(descendants.items(), key=lambda item: (item[1], item[0])))
    candidates.extend(siblings)

    seen: set[str] = set()
    ordered: list[str] = []
    for node_id in candidates:
        if node_id in seen:
            continue
        seen.add(node_id)
        ordered.append(node_id)
    truncated = len(ordered) > max_nodes
    return ordered[:max_nodes], truncated


def build_refactor_pack(
    root: Path,
    *,
    target_id: str | None = None,
    topic: str | None = None,
    include_staged: bool = False,
    ancestor_depth: int = 2,
    descendant_depth: int = 2,
    sibling_limit: int = 20,
    max_nodes: int = 80,
    include_lint: bool = True,
) -> dict[str, Any]:
    if not target_id and not topic:
        raise ValueError("refactor pack requires --target or --topic")
    if ancestor_depth < 0 or descendant_depth < 0:
        raise ValueError("depth values must be non-negative")
    if sibling_limit < 0 or max_nodes <= 0:
        raise ValueError("sibling-limit must be non-negative and max-nodes must be positive")

    nodes, staged_ids = _load_nodes(root, include_staged=include_staged)
    nodes_by_id = {node.id: node for node in nodes}
    loaded_ids = set(nodes_by_id)
    graph, graph_diags = build_graph(nodes)

    if target_id and target_id not in nodes_by_id:
        raise ValueError(f"target node not found in loaded nodes: {target_id}")

    topic_ids = _topic_selected(nodes, topic) if topic else set()
    target = nodes_by_id[target_id] if target_id else None
    direct_deps = sorted(graph.edges.get(target_id, [])) if target_id else []
    direct_dependents = sorted(graph.reverse_edges.get(target_id, [])) if target_id else []
    ancestors = (
        _bounded_walk(graph, target_id, direction="ancestors", max_depth=ancestor_depth)
        if target_id else {}
    )
    descendants = (
        _bounded_walk(graph, target_id, direction="descendants", max_depth=descendant_depth)
        if target_id else {}
    )

    siblings: list[str] = []
    if target is not None:
        target_home = home_topic_for_node(target)
        siblings = [
            node.id for node in sorted(nodes, key=lambda n: n.id)
            if node.id != target.id and home_topic_for_node(node) == target_home
        ][:sibling_limit]

    selected_ids, truncated = _ordered_ids(
        target_id=target_id,
        topic=topic,
        topic_ids=topic_ids,
        direct_deps=direct_deps,
        direct_dependents=direct_dependents,
        ancestors=ancestors,
        descendants=descendants,
        siblings=siblings,
        max_nodes=max_nodes,
    )
    selected_set = set(selected_ids)

    lint_findings: list[dict[str, Any]] = []
    if include_lint:
        lint_findings = _relevant_lint_findings(
            _run_lint(root),
            selected_ids=selected_set,
            loaded_ids=loaded_ids,
            topic_ids=topic_ids,
            include_staged=include_staged,
        )

    return {
        "kind": "mdblueprint-refactor-pack",
        "mode": "admitted+staged" if include_staged else "admitted",
        "knowledge_root": str(root),
        "target_id": target_id,
        "topic": topic,
        "allowed_inputs": ALLOWED_INPUTS + (
            ["docs/knowledge/staged/**/*.md as loaded provisional graph nodes"] if include_staged else []
        ),
        "staged_policy": {
            "included": include_staged,
            "graph_role": (
                "loaded nodes for dependency existence, reachability, topic, duplicate/overlap, and formulation-impact analysis"
                if include_staged
                else "outside loaded graph; consult a staged id index before writing missing-node requests"
            ),
            "admission_role": "staged nodes are not admitted truth and this pack does not propose promotion",
        },
        "forbidden_inputs": FORBIDDEN_INPUTS,
        "bounds": {
            "ancestor_depth": ancestor_depth,
            "descendant_depth": descendant_depth,
            "sibling_limit": sibling_limit,
            "max_nodes": max_nodes,
            "selected_node_count": len(selected_ids),
            "truncated": truncated,
        },
        "graph_diagnostics": [_diagnostic_payload(diag) for diag in graph_diags],
        "focus": {
            "direct_dependencies": direct_deps,
            "direct_dependents": direct_dependents,
            "transitive_ancestors": [
                {"node_id": node_id, "distance": distance}
                for node_id, distance in sorted(ancestors.items(), key=lambda item: (item[1], item[0]))
            ],
            "transitive_descendants": [
                {"node_id": node_id, "distance": distance}
                for node_id, distance in sorted(descendants.items(), key=lambda item: (item[1], item[0]))
            ],
            "sibling_topic_nodes": siblings,
            "topic_nodes": sorted(topic_ids),
        },
        "formulation_impact": {
            "review_recommended": bool(target_id and descendants),
            "reason": (
                "Target has descendants; graph reachability is only a first-pass impact signal."
                if target_id and descendants
                else "No target descendants loaded for formulation-impact review."
            ),
            "descendant_ids": sorted(descendants),
        },
        "lint_findings": lint_findings,
        "nodes": [
            _node_payload(nodes_by_id[node_id], graph, staged_ids=staged_ids, all_ids=loaded_ids)
            for node_id in selected_ids
            if node_id in nodes_by_id
        ],
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a bounded deterministic evidence bundle for graph refactor review."
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--target", dest="target_id")
    parser.add_argument("--topic")
    parser.add_argument("--include-staged", action="store_true")
    parser.add_argument("--ancestor-depth", type=int, default=2)
    parser.add_argument("--descendant-depth", type=int, default=2)
    parser.add_argument("--sibling-limit", type=int, default=20)
    parser.add_argument("--max-nodes", type=int, default=80)
    parser.add_argument("--no-lint", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pack = build_refactor_pack(
            args.knowledge_root,
            target_id=args.target_id,
            topic=args.topic,
            include_staged=args.include_staged,
            ancestor_depth=args.ancestor_depth,
            descendant_depth=args.descendant_depth,
            sibling_limit=args.sibling_limit,
            max_nodes=args.max_nodes,
            include_lint=not args.no_lint,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(pack, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
