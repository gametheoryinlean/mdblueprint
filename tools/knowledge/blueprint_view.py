"""Leanblueprint-style presentation view models."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.models import DEFINITION_KINDS, Node


THEOREM_LIKE_KINDS = frozenset({
    "lemma",
    "proposition",
    "theorem",
    "external-theorem",
})

NOT_READY_STATUSES = frozenset({
    "staged",
    "needs_statement_review",
    "needs_definition_review",
    "needs_proof_review",
    "blocked",
})


@dataclass(frozen=True)
class BlueprintNodeView:
    id: str
    html_id: str
    label: str
    title: str
    caption: str
    kind: str
    status: str
    shape: str
    target: str | None = None
    plan_status: str | None = None
    border_state: str | None = None
    fill_state: str | None = None
    lean_declarations: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlueprintGraphView:
    nodes: list[BlueprintNodeView] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    proof_plan_edges: list[tuple[str, str]] = field(default_factory=list)


def display_label(node_id: str) -> str:
    return node_id.rsplit(".", 1)[-1]


def html_id(node_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else f"-{ord(ch):x}-" for ch in node_id)
    return f"node-{safe}"


def dot_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def kind_caption(kind: str) -> str:
    return {
        "topic": "Topic",
        "concept": "Concept",
        "definition": "Definition",
        "lemma": "Lemma",
        "proposition": "Proposition",
        "theorem": "Theorem",
        "external-theorem": "External theorem",
        "proof-plan": "Proof plan",
        "example": "Example",
        "task": "Task",
    }.get(kind, kind.replace("-", " ").title())


def node_shape(kind: str) -> str:
    if kind in DEFINITION_KINDS:
        return "box"
    if kind in THEOREM_LIKE_KINDS:
        return "ellipse"
    if kind in {"example", "proof-plan"}:
        return "note"
    if kind == "task":
        return "component"
    return "box"


def _deps_ready(node: Node, g: KnowledgeGraph) -> bool:
    for dep_id in node.uses:
        dep = g.nodes.get(dep_id)
        if dep is None or dep.status in NOT_READY_STATUSES:
            return False
    return True


def _ancestors(node_id: str, g: KnowledgeGraph) -> set[str]:
    seen: set[str] = set()
    stack = list(g.edges.get(node_id, []))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(g.edges.get(current, []))
    return seen


def _border_state(node: Node, g: KnowledgeGraph) -> str | None:
    if node.status in {"formalized", "proved"}:
        return "stated"
    if node.status in NOT_READY_STATUSES:
        return "not_ready"
    if node.status == "admitted" and _deps_ready(node, g):
        return "can_state"
    return None


def _fill_state(node: Node, g: KnowledgeGraph) -> str | None:
    if node.kind in DEFINITION_KINDS and node.status in {"formalized", "proved"}:
        return "defined"
    if node.status == "proved":
        ancestor_ids = _ancestors(node.id, g)
        if all(
            g.nodes[ancestor_id].status in {"formalized", "proved"}
            or g.nodes[ancestor_id].kind in DEFINITION_KINDS
            for ancestor_id in ancestor_ids
        ):
            return "fully_proved"
        return "proved"
    if node.status == "admitted" and _deps_ready(node, g) and node.kind in THEOREM_LIKE_KINDS:
        return "can_prove"
    return None


def build_blueprint_graph(g: KnowledgeGraph) -> BlueprintGraphView:
    nodes: list[BlueprintNodeView] = []
    for node_id in sorted(g.nodes):
        node = g.nodes[node_id]
        lean_decls = tuple(node.lean.declarations) if node.lean else ()
        nodes.append(
            BlueprintNodeView(
                id=node.id,
                html_id=html_id(node.id),
                label=node.title,
                title=node.title,
                caption=kind_caption(node.kind),
                kind=node.kind,
                status=node.status,
                target=node.target,
                plan_status=node.plan_status,
                shape=node_shape(node.kind),
                border_state=_border_state(node, g),
                fill_state=_fill_state(node, g),
                lean_declarations=lean_decls,
                uses=tuple(sorted(g.edges.get(node.id, []))),
                used_by=tuple(sorted(g.reverse_edges.get(node.id, []))),
            )
        )

    edges: list[tuple[str, str]] = []
    for dependent in sorted(g.edges):
        for dependency in sorted(g.edges[dependent]):
            edges.append((dependency, dependent))

    proof_plan_edges = [
        (target_id, plan_id)
        for plan_id, target_id in sorted(g.proof_plan_targets.items())
    ]

    return BlueprintGraphView(nodes=nodes, edges=edges, proof_plan_edges=proof_plan_edges)


def dot_node_attributes(view: BlueprintNodeView) -> dict[str, str]:
    attrs = {
        "label": view.label,
        "shape": view.shape,
        "penwidth": "1.8",
        "URL": f"#{escape(view.html_id)}",
    }
    if view.border_state == "stated":
        attrs["color"] = "green"
    elif view.border_state == "can_state":
        attrs["color"] = "blue"
    elif view.border_state == "not_ready":
        attrs["color"] = "#FFAA33"

    if view.fill_state == "defined":
        attrs["fillcolor"] = "#B0ECA3"
        attrs["style"] = "filled"
    elif view.fill_state == "proved":
        attrs["fillcolor"] = "#9CEC8B"
        attrs["style"] = "filled"
    elif view.fill_state == "can_prove":
        attrs["fillcolor"] = "#A3D6FF"
        attrs["style"] = "filled"
    elif view.fill_state == "fully_proved":
        attrs["fillcolor"] = "#1CAC78"
        attrs["style"] = "filled"
    if view.kind == "proof-plan":
        attrs["style"] = "dashed"
        if view.plan_status == "selected":
            attrs["color"] = "blue"
            attrs["penwidth"] = "2.4"
    return attrs


def graph_to_dot(view: BlueprintGraphView) -> str:
    lines = [
        'strict digraph "" {',
        "\tgraph [bgcolor=transparent];",
        '\tnode [label="\\N", penwidth=1.8];',
        "\tedge [arrowhead=vee];",
    ]
    for node in view.nodes:
        attrs = dot_node_attributes(node)
        attr_text = ", ".join(f"{key}={dot_quote(value)}" for key, value in sorted(attrs.items()))
        lines.append(f"\t{dot_quote(node.id)} [{attr_text}];")
    for source, target in view.edges:
        lines.append(f"\t{dot_quote(source)} -> {dot_quote(target)} [style=dashed];")
    for source, target in view.proof_plan_edges:
        attrs = {
            "label": "has plan",
            "style": "dotted",
        }
        attr_text = ", ".join(f"{key}={dot_quote(value)}" for key, value in sorted(attrs.items()))
        lines.append(f"\t{dot_quote(source)} -> {dot_quote(target)} [{attr_text}];")
    lines.append("}")
    return "\n".join(lines)
