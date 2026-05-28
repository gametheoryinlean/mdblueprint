"""DAG builder and graph operations for knowledge nodes."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from tools.knowledge.models import MATH_KINDS, PROOF_PLAN_TARGET_KINDS, Node
from tools.knowledge.validator import Diagnostic


@dataclass
class KnowledgeGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    reverse_edges: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    proof_plan_targets: dict[str, str] = field(default_factory=dict)
    proof_plans_by_target: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def build_graph(nodes: list[Node]) -> tuple[KnowledgeGraph, list[Diagnostic]]:
    diags: list[Diagnostic] = []
    g = KnowledgeGraph()

    # Detect duplicate ids
    seen_ids: dict[str, Node] = {}
    for node in nodes:
        if not node.id:
            continue
        if node.id in seen_ids:
            prev = seen_ids[node.id]
            diags.append(Diagnostic(
                "error", node.id,
                f"duplicate node id (also in {prev.file_path})",
                node.file_path,
            ))
            continue
        seen_ids[node.id] = node
        g.nodes[node.id] = node

    # Build edges and check dependencies.
    #
    # Multi-candidate layout (issue #159): a candidate that is not yet
    # promoted is loaded into g.nodes but contributes NO edges in either
    # direction — its proof is not part of the verified DAG, and a
    # work-in-progress candidate may reference helpers that do not exist
    # yet. Only the promoted candidate (and ordinary nodes / canonicals)
    # contribute edges. The promoted candidate's edges are keyed by its
    # own id; the publisher resolves canonical → promoted-candidate.
    for nid, node in g.nodes.items():
        if node.candidate_of is not None and node.status != "promoted":
            continue
        for dep in node.uses:
            if dep not in g.nodes:
                level = "warning" if node.status == "staged" else "error"
                diags.append(Diagnostic(
                    level, nid,
                    f"dependency not found: {dep!r}",
                    node.file_path,
                ))
            else:
                g.edges[nid].append(dep)
                g.reverse_edges[dep].append(nid)

                # Task reference constraint
                dep_node = g.nodes[dep]
                if node.kind in MATH_KINDS and dep_node.kind == "task":
                    diags.append(Diagnostic(
                        "error", nid,
                        f"mathematical node references task node: {dep!r}",
                        node.file_path,
                    ))
                if node.kind in MATH_KINDS and node.kind != "proof-plan" and dep_node.kind == "proof-plan":
                    diags.append(Diagnostic(
                        "error", nid,
                        f"mathematical node uses proof-plan node as a dependency; "
                        f"proof-plan nodes must use target instead: {dep!r}",
                        node.file_path,
                    ))
                if node.kind == "proof-plan" and node.target == dep:
                    diags.append(Diagnostic(
                        "error", nid,
                        f"proof-plan cannot use its target as a dependency: {dep!r}",
                        node.file_path,
                    ))

    # Proof-plan attachment edges are typed separately from logical uses edges.
    for nid, node in g.nodes.items():
        if node.kind != "proof-plan":
            continue
        if not node.target:
            diags.append(Diagnostic(
                "error", nid,
                "proof-plan target is required",
                node.file_path,
            ))
            continue
        if node.target == nid:
            diags.append(Diagnostic(
                "error", nid,
                "proof-plan target cannot be itself",
                node.file_path,
            ))
            continue
        if node.target not in g.nodes:
            level = "warning" if node.status == "staged" else "error"
            diags.append(Diagnostic(
                level, nid,
                f"proof-plan target not found: {node.target!r}",
                node.file_path,
            ))
            continue
        target_node = g.nodes[node.target]
        if target_node.kind not in PROOF_PLAN_TARGET_KINDS:
            diags.append(Diagnostic(
                "error", nid,
                f"proof-plan target must be theorem-like, got {target_node.kind!r}: {node.target!r}",
                node.file_path,
            ))
            continue
        g.proof_plan_targets[nid] = node.target
        g.proof_plans_by_target[node.target].append(nid)

    for plan_ids in g.proof_plans_by_target.values():
        plan_ids.sort()

    # Cross-reference check for proved_via_plan markers: the referenced
    # plan must exist, be a proof-plan, and target this very node.
    for nid, node in g.nodes.items():
        if node.proved_via_plan is None:
            continue
        plan = g.nodes.get(node.proved_via_plan)
        if plan is None:
            diags.append(Diagnostic(
                "error", nid,
                f"proved_via_plan references unknown node: {node.proved_via_plan!r}",
                node.file_path,
            ))
            continue
        if plan.kind != "proof-plan":
            diags.append(Diagnostic(
                "error", nid,
                f"proved_via_plan must reference a proof-plan node; "
                f"{node.proved_via_plan!r} is kind={plan.kind!r}",
                node.file_path,
            ))
            continue
        if plan.target != nid:
            diags.append(Diagnostic(
                "error", nid,
                f"proved_via_plan references plan {node.proved_via_plan!r} "
                f"whose target is {plan.target!r}, not this node",
                node.file_path,
            ))

    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in g.nodes}
    parent: dict[str, str | None] = {nid: None for nid in g.nodes}

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        for v in g.edges.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                cycle = [v, u]
                p = parent.get(u)
                while p is not None and p != v:
                    cycle.append(p)
                    p = parent.get(p)
                cycle.reverse()
                return cycle
            if color[v] == WHITE:
                parent[v] = u
                result = dfs(v)
                if result is not None:
                    return result
        color[u] = BLACK
        return None

    for nid in g.nodes:
        if color.get(nid) == WHITE:
            cycle = dfs(nid)
            if cycle is not None:
                cycle_str = " -> ".join(cycle)
                diags.append(Diagnostic(
                    "error", cycle[0],
                    f"dependency cycle: {cycle_str}",
                ))
                break

    return g, diags


def topological_sort(g: KnowledgeGraph) -> list[str]:
    in_degree: dict[str, int] = {nid: 0 for nid in g.nodes}
    for nid, deps in g.edges.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[nid] = in_degree.get(nid, 0)

    # Kahn's algorithm
    for nid, deps in g.edges.items():
        for dep in deps:
            if dep in in_degree:
                pass  # edges go from nid -> dep (nid uses dep)

    # Recompute: in_degree[nid] = number of nodes that nid depends on
    # For topological sort, we want nodes with no remaining dependencies first
    in_deg: dict[str, int] = {nid: 0 for nid in g.nodes}
    for nid, deps in g.edges.items():
        for dep in deps:
            if dep in in_deg:
                in_deg[nid] += 1

    # BFS-based topological sort (dependencies before dependents)
    # A node is ready when all its dependencies are processed
    # Actually, we want: dep before nid. So reverse: in_deg of nid = len(edges[nid])
    # and we process nid when all deps are done.
    # Use reverse_edges to know who depends on a dep.
    ready: list[str] = sorted(nid for nid, d in in_deg.items() if d == 0)
    result: list[str] = []
    remaining = dict(in_deg)

    while ready:
        nid = ready.pop(0)
        result.append(nid)
        for dependent in sorted(g.reverse_edges.get(nid, [])):
            if dependent in remaining:
                remaining[dependent] -= 1
                if remaining[dependent] == 0:
                    ready.append(dependent)

    return result
