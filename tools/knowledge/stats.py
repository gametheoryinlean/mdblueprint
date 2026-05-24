"""Structural statistics CLI for mdblueprint knowledge bases.

Computes totals, kind/topic histograms, hot spots (in-degree / out-degree),
DAG depth, orphan count, and verification status summary.

Usage:
    mdblueprint-stats <knowledge_root> [--top N] [--json] [--no-include-staged]
"""
from __future__ import annotations

import argparse
import json as _json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.models import ADMITTED_STATUSES, Node
from tools.knowledge.parser import scan_directory


# ── Loading ───────────────────────────────────────────────────────────────────


def _load_nodes(root: Path, *, include_staged: bool) -> list[Node]:
    """Load nodes from nodes/ and optionally staged/ subdirectories."""
    nodes: list[Node] = []
    nodes_dir = root / "nodes"
    if nodes_dir.exists():
        nodes.extend(scan_directory(nodes_dir))
    if include_staged:
        staged_dir = root / "staged"
        if staged_dir.exists():
            nodes.extend(scan_directory(staged_dir))
    return nodes


# ── DAG metrics ───────────────────────────────────────────────────────────────


def _dag_longest_path(graph: KnowledgeGraph) -> int:
    """Return the number of edges on the longest path in the dependency DAG.

    Edges go from a node to its dependencies (node.uses).  The longest path is
    computed via topological ordering + DP over that ordering.

    Returns 0 for an empty graph or a graph with no edges.
    """
    if not graph.nodes:
        return 0

    # Build in-degree wrt edges (nid -> dep means nid depends on dep).
    # For topo sort we want to process deps before dependents.
    # We use reverse: in_deg[nid] = number of *dependencies* of nid that have
    # not yet been "released".
    in_deg: dict[str, int] = {nid: 0 for nid in graph.nodes}
    for nid, deps in graph.edges.items():
        in_deg[nid] = len(deps)

    # Kahn's topo sort: deps first, then nodes that use them.
    # We process a node when all its deps are done.
    ready = [nid for nid, d in sorted(in_deg.items()) if d == 0]
    dist: dict[str, int] = {nid: 0 for nid in graph.nodes}
    result: list[str] = []

    # remaining in-degree counter (mutable copy)
    rem = dict(in_deg)

    while ready:
        nid = ready.pop(0)
        result.append(nid)
        # nid is now processed; notify its reverse-edges (nodes that use nid).
        for dependent in sorted(graph.reverse_edges.get(nid, [])):
            if dependent not in rem:
                continue
            # dist[dependent] = max over all its deps of dist[dep] + 1
            dist[dependent] = max(dist[dependent], dist[nid] + 1)
            rem[dependent] -= 1
            if rem[dependent] == 0:
                ready.append(dependent)

    return max(dist.values(), default=0)


def _orphan_count(graph: KnowledgeGraph) -> int:
    """Count nodes with both in-degree == 0 and out-degree == 0."""
    count = 0
    for nid in graph.nodes:
        has_out = bool(graph.edges.get(nid))
        has_in = bool(graph.reverse_edges.get(nid))
        if not has_out and not has_in:
            count += 1
    return count


# ── Hot spots ─────────────────────────────────────────────────────────────────


def _top_by_in_degree(graph: KnowledgeGraph, top_n: int) -> list[tuple[str, int]]:
    """Return top_n nodes by number of nodes that *use* them (reverse-edge count).

    Sorted descending by count, then alphabetically by id for stable ties.
    """
    counts = {nid: len(graph.reverse_edges.get(nid, [])) for nid in graph.nodes}
    sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return sorted_items[:top_n] if top_n > 0 else []


def _top_by_out_degree(graph: KnowledgeGraph, top_n: int) -> list[tuple[str, int]]:
    """Return top_n nodes by number of dependencies they declare (edge count).

    Sorted descending by count, then alphabetically by id for stable ties.
    """
    counts = {nid: len(graph.edges.get(nid, [])) for nid in graph.nodes}
    sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return sorted_items[:top_n] if top_n > 0 else []


# ── Stats computation ─────────────────────────────────────────────────────────


def compute_stats(nodes: list[Node], graph: KnowledgeGraph, *, top_n: int = 10) -> dict[str, Any]:
    """Compute all statistics and return a structured dict.

    The dict structure mirrors the text output sections:
      totals, kinds, topics, verification, hot_spots_in_degree,
      hot_spots_out_degree, dag.
    """
    total = len(nodes)
    admitted = sum(1 for n in nodes if n.status in ADMITTED_STATUSES)
    staged = total - admitted

    # Kind histogram
    kind_counts: Counter[str] = Counter(n.kind for n in nodes)

    # Topic histogram: primary_topic (skip None)
    topic_counts: Counter[str] = Counter(
        n.primary_topic for n in nodes if n.primary_topic
    )
    topics_in_use = len(topic_counts)

    # Verification status summary
    stmt_accepted = sum(
        1 for n in nodes
        if n.verification and n.verification.statement == "accepted"
    )
    proof_accepted = sum(
        1 for n in nodes
        if n.verification and n.verification.proof == "accepted"
    )
    alignment_aligned = sum(
        1 for n in nodes
        if n.verification and n.verification.alignment == "aligned"
    )

    # Hot spots
    hot_in = _top_by_in_degree(graph, top_n)
    hot_out = _top_by_out_degree(graph, top_n)

    # DAG metrics
    depth = _dag_longest_path(graph)
    orphans = _orphan_count(graph)

    return {
        "totals": {
            "nodes": total,
            "admitted": admitted,
            "staged": staged,
            "topics_in_use": topics_in_use,
        },
        "kinds": dict(kind_counts.most_common()),
        "topics": dict(topic_counts.most_common()),
        "verification": {
            "statement_accepted": stmt_accepted,
            "proof_accepted": proof_accepted,
            "alignment_aligned": alignment_aligned,
            "total": total,
        },
        "hot_spots_in_degree": [
            {"node_id": nid, "count": cnt} for nid, cnt in hot_in
        ],
        "hot_spots_out_degree": [
            {"node_id": nid, "count": cnt} for nid, cnt in hot_out
        ],
        "dag": {
            "depth": depth,
            "orphans": orphans,
        },
    }


# ── Renderers ─────────────────────────────────────────────────────────────────


def _fmt_section(title: str) -> str:
    return f"── {title} ──"


def render_text(stats: dict[str, Any], *, top_n: int = 10) -> str:
    lines: list[str] = []

    # Totals
    t = stats["totals"]
    lines.append(_fmt_section("Totals"))
    lines.append(f"  Nodes: {t['nodes']} (admitted {t['admitted']}, staged {t['staged']})")
    lines.append(f"  Topics in use: {t['topics_in_use']}")
    lines.append("")

    # Kinds
    lines.append(_fmt_section("Kinds"))
    for kind, count in stats["kinds"].items():
        lines.append(f"  {kind:<20} {count}")
    lines.append("")

    # Hot spots — most depended upon
    lines.append(_fmt_section(f"Top {top_n} — most depended upon"))
    hot_in = stats["hot_spots_in_degree"]
    if hot_in:
        for entry in hot_in:
            lines.append(f"  {entry['count']:<4} {entry['node_id']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # Hot spots — depend on the most
    lines.append(_fmt_section(f"Top {top_n} — depend on the most"))
    hot_out = stats["hot_spots_out_degree"]
    if hot_out:
        for entry in hot_out:
            lines.append(f"  {entry['count']:<4} {entry['node_id']}")
    else:
        lines.append("  (none)")
    lines.append("")

    # DAG
    d = stats["dag"]
    lines.append(_fmt_section("DAG"))
    lines.append(f"  Depth (longest path):  {d['depth']}")
    lines.append(f"  Orphans (no in/out edges):  {d['orphans']}")
    lines.append("")

    # Verification
    v = stats["verification"]
    total = v["total"]
    lines.append(_fmt_section("Verification"))
    lines.append(f"  Statement accepted:  {v['statement_accepted']} of {total}")
    lines.append(f"  Proof accepted:      {v['proof_accepted']} of {total}")
    lines.append(f"  Alignment aligned:   {v['alignment_aligned']} of {total}")

    return "\n".join(lines)


def render_json(stats: dict[str, Any]) -> str:
    return _json.dumps(stats, ensure_ascii=False, indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mdblueprint-stats",
        description="Surface structural statistics and hot spots for a mdblueprint knowledge base.",
    )
    ap.add_argument(
        "knowledge_root",
        type=Path,
        help="Path to the knowledge base root (containing nodes/ and staged/).",
    )
    ap.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of entries to show per hot-spot list (default: 10).",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object instead of grouped text.",
    )
    staged_group = ap.add_mutually_exclusive_group()
    staged_group.add_argument(
        "--include-staged",
        dest="include_staged",
        action="store_true",
        default=True,
        help="Include staged nodes in statistics (default).",
    )
    staged_group.add_argument(
        "--no-include-staged",
        dest="include_staged",
        action="store_false",
        help="Exclude staged nodes; restrict to admitted nodes only.",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    nodes = _load_nodes(args.knowledge_root, include_staged=args.include_staged)
    graph, _diags = build_graph(nodes)
    stats = compute_stats(nodes, graph, top_n=args.top)

    if args.json:
        print(render_json(stats))
    else:
        print(render_text(stats, top_n=args.top))

    return 0


if __name__ == "__main__":
    sys.exit(main())
