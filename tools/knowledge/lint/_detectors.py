"""Built-in lint detectors and their private string/graph-walk helpers."""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from tools.knowledge.blueprint_view import plan_provides_proof
from tools.knowledge.export import child_topic_id, home_topic_for_node
from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.models import ADMITTED_STATUSES, STAGED_STATUSES, Node
from tools.knowledge.validator import Diagnostic

LlmRunner = Callable[[str], str]

# ── String normalisation helpers ──────────────────────────────────────────────

_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_TRAILING_PUNCT_RE = re.compile(r"^[\s\W_]+|[\s\W_]+$", flags=re.UNICODE)


def _normalize(text: str) -> str:
    """Lowercase, collapse internal whitespace, strip leading/trailing punctuation.

    Internal punctuation is preserved so semantically distinct sentences with
    similar surface words still stay apart.
    """
    if text is None:
        return ""
    lowered = text.lower()
    stripped = _LEADING_TRAILING_PUNCT_RE.sub("", lowered)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _ratio(a: str, b: str) -> float:
    """SequenceMatcher ratio over already-normalized strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


_STATEMENT_HEADING_RE = re.compile(r"^##\s+statement\b", flags=re.IGNORECASE | re.MULTILINE)
_HEADING_RE = re.compile(r"^#+\s", flags=re.MULTILINE)


def _statement_text(node: Node) -> str:
    """Return the body text under a `## Statement` section if present, else `""`.

    Used as a secondary similarity signal when titles alone don't trigger.
    """
    body = node.body or ""
    match = _STATEMENT_HEADING_RE.search(body)
    if match is None:
        return ""
    start = match.end()
    # Stop at the next heading of any level.
    next_heading = _HEADING_RE.search(body, pos=start)
    end = next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


# ── Graph-walk helper ─────────────────────────────────────────────────────────

def _path_exists_excluding_direct(
    graph: KnowledgeGraph,
    *,
    start: str,
    goal: str,
    excluded_first_hop: str,
) -> bool:
    """Return True iff there is a path start -> ... -> goal in the `uses` graph
    that does not begin with the direct edge start -> excluded_first_hop.

    The `uses` graph stores ``edges[u]`` as the prerequisites of ``u``.
    BFS therefore walks toward the start node's transitive prerequisites.
    """
    seen: set[str] = {start}
    queue: deque[str] = deque()
    for neighbor in graph.edges.get(start, ()):
        if neighbor == excluded_first_hop:
            continue
        if neighbor == goal:
            return True
        if neighbor not in seen:
            seen.add(neighbor)
            queue.append(neighbor)
    while queue:
        current = queue.popleft()
        for neighbor in graph.edges.get(current, ()):
            if neighbor == goal:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False


# ── Detector dataclasses ──────────────────────────────────────────────────────

@dataclass
class FuzzyTitleDupDetector:
    """Flag admitted node pairs with near-duplicate titles or statements."""

    threshold: float = 0.92
    code: str = "LINT_FUZZY_DUP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        out: list[Diagnostic] = []
        for index, a in enumerate(admitted):
            a_title = _normalize(a.title)
            a_stmt = _normalize(_statement_text(a))
            for b in admitted[index + 1:]:
                b_title = _normalize(b.title)
                score = _ratio(a_title, b_title)
                if score < self.threshold:
                    b_stmt = _normalize(_statement_text(b))
                    if a_stmt and b_stmt:
                        score = max(score, _ratio(a_stmt, b_stmt))
                if score >= self.threshold:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=a.id,
                        message=f"near-duplicate of {b.id!r} (similarity {score:.2f})",
                        file_path=a.file_path,
                        code=self.code,
                        related=(b.id,),
                    ))
        return out


@dataclass
class StagedAdmittedOverlapDetector:
    """Flag staged candidate nodes that re-state an already-admitted node."""

    threshold: float = 0.92
    code: str = "LINT_STAGED_OVERLAP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        staged = sorted(
            (n for n in nodes if n.status in STAGED_STATUSES),
            key=lambda n: n.id,
        )
        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        out: list[Diagnostic] = []
        for candidate in staged:
            c_title = _normalize(candidate.title)
            c_stmt = _normalize(_statement_text(candidate))
            for existing in admitted:
                e_title = _normalize(existing.title)
                score = _ratio(c_title, e_title)
                if score < self.threshold:
                    e_stmt = _normalize(_statement_text(existing))
                    if c_stmt and e_stmt:
                        score = max(score, _ratio(c_stmt, e_stmt))
                if score >= self.threshold:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=candidate.id,
                        message=(
                            f"staged candidate appears to overlap with admitted "
                            f"{existing.id!r} (similarity {score:.2f})"
                        ),
                        file_path=candidate.file_path,
                        code=self.code,
                        related=(existing.id,),
                    ))
        return out


@dataclass
class RedundantDepDetector:
    """Flag direct `uses` edges that are already implied by a transitive path."""

    code: str = "LINT_REDUNDANT_DEP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        # Iterate in deterministic order so diagnostic ordering is stable.
        for dependent_id in sorted(graph.edges):
            direct_deps = sorted(graph.edges.get(dependent_id, ()))
            if len(direct_deps) < 2:
                # A node with at most one direct dependency cannot have a
                # redundant direct edge: there is no second path candidate.
                continue
            for prereq in direct_deps:
                if _path_exists_excluding_direct(
                    graph,
                    start=dependent_id,
                    goal=prereq,
                    excluded_first_hop=prereq,
                ):
                    node = graph.nodes.get(dependent_id)
                    out.append(Diagnostic(
                        level="info",
                        node_id=dependent_id,
                        message=(
                            f"direct dependency on {prereq!r} is redundant; "
                            f"{dependent_id!r} already reaches it transitively"
                        ),
                        file_path=node.file_path if node is not None else None,
                        code=self.code,
                        related=(prereq,),
                    ))
        return out


@dataclass
class OrphanDetector:
    """Flag nodes with no incoming `uses` edges and no outgoing `uses` edges.

    Proof-plan attachments (target / proof_plan_targets / proof_plans_by_target)
    are intentionally considered non-orphan even when uses is empty: a plan
    attached to a theorem is not stranded, and a theorem with at least one
    candidate plan is being actively reasoned about.
    """

    code: str = "LINT_ORPHAN"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            if graph.edges.get(node_id):
                continue  # has out-degree
            if graph.reverse_edges.get(node_id):
                continue  # has in-degree
            if node_id in graph.proof_plan_targets:
                continue  # is a plan attached to some target
            if graph.proof_plans_by_target.get(node_id):
                continue  # is a target carrying at least one plan
            out.append(Diagnostic(
                level="info",
                node_id=node_id,
                message=f"node {node_id!r} has no incoming or outgoing dependencies",
                file_path=node.file_path,
                code=self.code,
            ))
        return out


# ── Lean ref kind detector ────────────────────────────────────────────────────

_LEAN_KINDS_FOR_DEFINITION = frozenset(
    {"def", "abbrev", "structure", "class", "inductive", "instance"}
)
_LEAN_KINDS_FOR_THEOREM = frozenset({"theorem", "lemma"})

_LEAN_KIND_CLASSES: dict[str, frozenset[str]] = {
    "definition": _LEAN_KINDS_FOR_DEFINITION,
    "concept": _LEAN_KINDS_FOR_DEFINITION,
    "lemma": _LEAN_KINDS_FOR_THEOREM,
    "proposition": _LEAN_KINDS_FOR_THEOREM,
    "theorem": _LEAN_KINDS_FOR_THEOREM,
    "external-theorem": _LEAN_KINDS_FOR_THEOREM,
}


def _resolve_declaration(decl: str, index: LeanIndex) -> LeanDeclaration | None:
    """Resolve a (possibly unqualified) declaration name against an index.

    Mirrors tools.knowledge.lean_check._matching_declarations: prefer an
    exact qualified-name hit; fall back to suffix matches ending in
    ``.<decl>``. Returns ``None`` when the lookup is ambiguous or has no
    match — both cases are handled elsewhere (``check.py`` reports
    ambiguity / missing names).
    """
    exact = index.declarations.get(decl)
    if exact is not None:
        return exact
    suffix = f".{decl}"
    matches = [d for qn, d in index.declarations.items() if qn.endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    return None


@dataclass
class LeanRefKindDetector:
    """Flag nodes whose Lean declaration kind contradicts the node's mdblueprint kind."""

    indexes: dict[str, LeanIndex] | None = None
    code: str = "LINT_LEAN_KIND"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        if not self.indexes:
            return [Diagnostic(
                level="info",
                node_id="",
                message="lean index not available; skipping LINT_LEAN_KIND",
                code=self.code,
            )]

        default_index = self.indexes.get("default") or next(
            iter(self.indexes.values()), None
        )
        out: list[Diagnostic] = []
        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            expected = _LEAN_KIND_CLASSES.get(node.kind)
            if expected is None:
                continue
            if node.lean is None or not node.lean.declarations:
                continue

            repo_id = node.lean.repository
            index = (
                self.indexes.get(repo_id) if repo_id is not None else default_index
            )
            if index is None:
                continue

            for decl_name in node.lean.declarations:
                resolved = _resolve_declaration(decl_name, index)
                if resolved is None:
                    continue
                if resolved.kind not in expected:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=node.id,
                        message=(
                            f"node kind {node.kind!r} expects a Lean "
                            f"{'/'.join(sorted(expected))} declaration; "
                            f"{decl_name!r} is a Lean {resolved.kind!r}"
                        ),
                        file_path=node.file_path,
                        code=self.code,
                        related=(decl_name,),
                    ))
        return out


# ── PlanPromoteDetector (PR 8 / closes #127) ─────────────────────────────────

_PLAN_PROMOTE_VALID_SEVERITIES = frozenset({"info", "warning"})
_PLAN_PROMOTE_TARGET_KINDS = frozenset(
    {"lemma", "proposition", "theorem", "external-theorem"}
)


def _canonical_plan_for_target(target_id: str, graph: KnowledgeGraph) -> str | None:
    """Mirror tools.knowledge.promote_via_plan._canonical_plan."""
    candidates = [
        plan_id
        for plan_id in graph.proof_plans_by_target.get(target_id, [])
        if plan_provides_proof(plan_id, graph)
    ]
    if not candidates:
        return None
    selected = sorted(
        plan_id for plan_id in candidates
        if graph.nodes[plan_id].plan_status == "selected"
    )
    if selected:
        return selected[0]
    return sorted(candidates)[0]


@dataclass
class PlanPromoteDetector:
    """Nudge authors to run ``promote_via_plan`` (or hand-write status=proved)
    when an attached plan already supplies a complete Lean proof."""

    severity: str = "info"
    code: str = "LINT_PLAN_PROMOTE"
    needs_llm: bool = False

    def __post_init__(self) -> None:
        if self.severity not in _PLAN_PROMOTE_VALID_SEVERITIES:
            raise ValueError(
                f"PlanPromoteDetector severity must be 'info' or 'warning', "
                f"got {self.severity!r}"
            )

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            if node.kind not in _PLAN_PROMOTE_TARGET_KINDS:
                continue
            if node.status == "proved":
                continue
            plan_id = _canonical_plan_for_target(node.id, graph)
            if plan_id is None:
                continue
            out.append(Diagnostic(
                level=self.severity,
                node_id=node.id,
                message=(
                    f"plan {plan_id!r} provides a complete Lean proof for "
                    f"{node.id!r} (status={node.status!r}). Consider running "
                    f"`uv run python -m tools.knowledge.promote_via_plan` "
                    f"or setting `status: proved` + "
                    f"`proved_via_plan: {plan_id}` manually."
                ),
                file_path=node.file_path,
                code=self.code,
                related=(plan_id,),
            ))
        return out



# ── HierarchyInversionDetector (closes #137) ────────────────────────────────

_HIERARCHY_VALID_SEVERITIES = frozenset({"info", "warning"})


@dataclass
class HierarchyInversionDetector:
    """Flag uses-edges where parent-topic content depends on subtopic content.

    For every uses edge ``u → v`` (i.e. ``v.uses`` lists ``u``), the prereq
    ``u`` living in a strict descendant of the dependent's home topic is
    almost always an editorial mistake: the parent-topic node should either
    live in the subtopic (move its ``primary_topic``) or not depend on the
    specialised material at all.
    """

    severity: str = "warning"
    code: str = "LINT_HIERARCHY_INVERSION"
    needs_llm: bool = False

    def __post_init__(self) -> None:
        if self.severity not in _HIERARCHY_VALID_SEVERITIES:
            raise ValueError(
                f"HierarchyInversionDetector severity must be 'info' or 'warning', "
                f"got {self.severity!r}"
            )

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        for dependent_id in sorted(graph.edges):
            dependent = graph.nodes.get(dependent_id)
            if dependent is None:
                continue
            h_v = home_topic_for_node(dependent)
            for dependency_id in sorted(graph.edges[dependent_id]):
                dependency = graph.nodes.get(dependency_id)
                if dependency is None:
                    continue
                h_u = home_topic_for_node(dependency)
                if h_u == h_v:
                    continue
                if not h_u.startswith(f"{h_v}."):
                    continue
                out.append(Diagnostic(
                    level=self.severity,
                    node_id=dependent_id,
                    message=(
                        f"node {dependent_id!r} (home: {h_v!r}) depends on "
                        f"{dependency_id!r} which lives in subtopic {h_u!r}; "
                        f"consider moving {dependent_id!r} down into {h_u!r} "
                        f"(or a common ancestor) or removing the dependency"
                    ),
                    file_path=dependent.file_path,
                    code=self.code,
                    related=(dependency_id,),
                ))
        return out


# ── TopicCycleDetector (closes #138) ────────────────────────────────────────


@dataclass
class TopicCycleDetector:
    """Flag aggregation-level symmetric cycles between sibling child topics.

    Walks every parent topic whose nodes have ≥ 2 distinct child-topic homes,
    rebuilds the per-child uses-edge aggregation, and emits one info-level
    diagnostic per ``(child_a, child_b)`` symmetric pair. The underlying
    node-level DAG remains acyclic; the cycle is a property of the rollup.
    """

    code: str = "LINT_TOPIC_CYCLE"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        # Collect every (parent_topic, child_a, child_b) edge implied by
        # node-level uses edges.
        per_parent: dict[str, set[tuple[str, str]]] = {}
        for dependent_id in sorted(graph.edges):
            dependent = graph.nodes.get(dependent_id)
            if dependent is None or dependent.kind == "proof-plan":
                continue
            h_v = home_topic_for_node(dependent)
            for dependency_id in sorted(graph.edges[dependent_id]):
                dependency = graph.nodes.get(dependency_id)
                if dependency is None or dependency.kind == "proof-plan":
                    continue
                h_u = home_topic_for_node(dependency)
                if h_u == h_v:
                    continue
                # Find every parent topic under which BOTH nodes resolve to
                # *distinct* immediate children.
                for parent in _common_strict_prefixes(h_u, h_v):
                    child_u = child_topic_id(parent, h_u)
                    child_v = child_topic_id(parent, h_v)
                    if child_u is None or child_v is None or child_u == child_v:
                        continue
                    per_parent.setdefault(parent, set()).add((child_u, child_v))

        out: list[Diagnostic] = []
        for parent in sorted(per_parent):
            edge_set = per_parent[parent]
            seen_pairs: set[tuple[str, str]] = set()
            for child_u, child_v in sorted(edge_set):
                if (child_v, child_u) in edge_set:
                    pair = tuple(sorted([child_u, child_v]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    a, b = pair
                    out.append(Diagnostic(
                        level="info",
                        node_id="",
                        message=(
                            f"sibling subtopics {a!r} and {b!r} of {parent!r} "
                            f"aggregate into a cycle (a↔b at child-topic level); "
                            f"the underlying node-level DAG remains acyclic"
                        ),
                        code=self.code,
                    ))
        return out


def _common_strict_prefixes(topic_a: str, topic_b: str) -> list[str]:
    """Return every topic id ``P`` such that both ``topic_a`` and ``topic_b``
    are strict descendants of ``P``."""
    parts_a = topic_a.split(".")
    parts_b = topic_b.split(".")
    common: list[str] = []
    for index in range(min(len(parts_a), len(parts_b))):
        if parts_a[index] != parts_b[index]:
            break
        # We need P such that both a and b strictly descend from P,
        # meaning P is a STRICT prefix of both — index < len-1 of each.
        if index < len(parts_a) - 1 and index < len(parts_b) - 1:
            common.append(".".join(parts_a[: index + 1]))
    return common
