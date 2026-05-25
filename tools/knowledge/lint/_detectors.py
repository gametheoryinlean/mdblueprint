"""Built-in lint detectors and their private string/graph-walk helpers."""
from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Callable

from tools.knowledge.blueprint_view import plan_provides_proof
from tools.knowledge.export import child_topic_id, home_topic_for_node
from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.models import ADMITTED_STATUSES, STAGED_STATUSES, Node
from tools.knowledge.node_refs import NODE_REF_RE
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



# ── ProseDepConsistencyDetector (closes #121 item 5) ─────────────────────────


@dataclass
class ProseDepConsistencyDetector:
    """Flag body ``[[node:X]]`` references whose target is not in the node's
    ``uses`` field.

    Covers all node kinds and the full body text (not just proof sections).
    The existing ``check_node_body_refs`` already handles theorem-kind nodes'
    proof sections as an *error* in the publish gate; this detector is a
    softer *warning* over the full body for all kinds, running on the lint
    surface in parallel.

    Deduplicates within a single run: at most one diagnostic per
    ``(node.id, target_id)`` pair, even when the ref appears multiple times.
    """

    code: str = "LINT_PROSE_DEP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        all_ids: frozenset[str] = frozenset(n.id for n in nodes)
        out: list[Diagnostic] = []
        for node in sorted(nodes, key=lambda n: n.id):
            if not node.body:
                continue
            uses_set: set[str] = set(node.uses or [])
            seen: set[str] = set()
            for m in NODE_REF_RE.finditer(node.body):
                target = m.group(1)
                if target == node.id:
                    continue
                if target not in all_ids:
                    # Unknown ref — check.py already errors on these; don't
                    # double-report here.
                    continue
                if target in uses_set:
                    continue
                if target in seen:
                    continue
                seen.add(target)
                out.append(Diagnostic(
                    level="warning",
                    node_id=node.id,
                    message=(
                        f"body references [[node:{target}]] but "
                        f"{target!r} is not listed in uses"
                    ),
                    file_path=node.file_path,
                    code=self.code,
                    related=(target,),
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


# ── Lean/blueprint root alias table ──────────────────────────────────────────

# Maps Lean singular-convention roots to blueprint plural-convention roots.
# The normalization function canonicalises both sides to the blueprint form
# (plural) before comparison.
#
# These are pure grammatical normalization entries covering cases where Lean
# idiom uses a singular module name while the corresponding blueprint topic
# uses the plural form.  Project-level overrides can be passed to the
# detector dataclasses via ``extra_aliases`` (which wins on conflict).
_BLUEPRINT_LEAN_ROOT_ALIASES: dict[str, str] = {
    # Singular Lean module root → plural blueprint topic root.
    # Lean idiom conventionally uses singular module names; blueprint topics
    # conventionally use the plural form.
    "strategic_game": "strategic_games",
    "extensive_game": "extensive_games",
    "repeated_game": "repeated_games",
    "stochastic_game": "stochastic_games",
    "coalitional_game": "coalitional_games",
    "bayesian_game": "bayesian_games",
    "differential_game": "differential_games",
}

# Reverse mapping (plural → singular) derived from the table above.
_LEAN_BLUEPRINT_ROOT_ALIASES_REVERSE: dict[str, str] = {
    v: k for k, v in _BLUEPRINT_LEAN_ROOT_ALIASES.items()
}


def _canonical_root(root: str, extra_aliases: dict[str, str] | None = None) -> str:
    """Canonicalise a root to blueprint plural form using the alias table.

    If the root is a known Lean-singular form (in the built-in table or
    ``extra_aliases``), return the plural.  ``extra_aliases`` wins over the
    built-in table on conflict.
    If the root is already a plural form, return it as-is.
    """
    if extra_aliases and root in extra_aliases:
        return extra_aliases[root]
    return _BLUEPRINT_LEAN_ROOT_ALIASES.get(root, root)


_PASCAL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _pascal_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case, e.g. 'LinearAlgebra' → 'linear_algebra'."""
    return _PASCAL_SPLIT_RE.sub("_", name).lower()


def _lean_module_to_normalized_root(
    module: str,
    extra_aliases: dict[str, str] | None = None,
) -> str | None:
    """Derive the normalised topic root from a Lean module name.

    Steps:
    1. Strip the first segment (project prefix): ``EconCSLib.LinearAlgebra.Farkas``
       → ``LinearAlgebra.Farkas``.
    2. Convert PascalCase to snake_case: ``LinearAlgebra.Farkas``
       → ``linear_algebra.farkas``.
    3. Drop the last segment (file/declaration name): ``linear_algebra.farkas``
       → ``linear_algebra``.
    4. Take the first segment as ``lean_root``: ``linear_algebra``.
    5. Canonicalise via alias table (``extra_aliases`` wins on conflict).

    Returns ``None`` when the module has fewer than 2 segments after stripping
    the project prefix (nothing meaningful to compare).
    """
    parts = module.split(".")
    if len(parts) < 2:
        return None
    # Strip project prefix (first segment)
    without_prefix = parts[1:]
    if not without_prefix:
        return None
    # Convert each segment to snake_case
    snake_parts = [_pascal_to_snake(p) for p in without_prefix]
    # Drop the last segment (declaration/file name)
    if len(snake_parts) == 1:
        # Only one segment after the project prefix → that IS the root already
        lean_root = snake_parts[0]
    else:
        lean_root = snake_parts[0]
    return _canonical_root(lean_root, extra_aliases)


# ── TopicLeanAlignmentDetector ────────────────────────────────────────────────


@dataclass
class TopicLeanAlignmentDetector:
    """Flag nodes whose blueprint topic root does not match the Lean module root.

    For each node with at least one ``lean.modules`` entry, computes the
    blueprint root (first segment of the node's home topic) and the Lean root
    (first meaningful PascalCase segment of the Lean module, snake-cased and
    alias-normalised). If *none* of the node's Lean modules produces a
    matching root, a warning is emitted.

    Opt-out: set ``topic_lean_alignment: divergent`` in the node frontmatter
    to suppress the check for that node.

    ``extra_aliases`` is merged on top of the built-in
    ``_BLUEPRINT_LEAN_ROOT_ALIASES`` table (extra wins on conflict). Use it
    to pass project-level ``lint.topic_lean_aliases`` from the config.
    """

    code: str = "LINT_TOPIC_LEAN_ALIGNMENT"
    needs_llm: bool = False
    extra_aliases: dict[str, str] = field(default_factory=dict)

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        aliases = self.extra_aliases or None
        out: list[Diagnostic] = []
        for node in sorted(nodes, key=lambda n: n.id):
            # Opt-out
            if node.topic_lean_alignment == "divergent":
                continue
            # Only check nodes with at least one Lean module
            if node.lean is None or not node.lean.modules:
                continue

            home_topic = home_topic_for_node(node)
            blueprint_root = _canonical_root(home_topic.split(".")[0], aliases)

            # Check whether any Lean module matches
            mismatched_modules: list[str] = []
            for module in node.lean.modules:
                lean_root = _lean_module_to_normalized_root(module, aliases)
                if lean_root is None:
                    continue
                if lean_root == blueprint_root:
                    # At least one match — node is aligned
                    mismatched_modules = []
                    break
                mismatched_modules.append(module)

            if not mismatched_modules:
                continue

            # Emit one warning per mismatched module
            for module in mismatched_modules:
                lean_root = _lean_module_to_normalized_root(module, aliases) or "?"
                out.append(Diagnostic(
                    level="warning",
                    node_id=node.id,
                    message=(
                        f"blueprint root {blueprint_root!r} but Lean module "
                        f"{module!r} normalises to root {lean_root!r} — "
                        f"move blueprint to {lean_root!r}.*, "
                        f"move Lean to project prefix + {blueprint_root!r}.*, "
                        f"or add topic_lean_alignment: divergent"
                    ),
                    file_path=node.file_path,
                    code=self.code,
                    related=(module,),
                ))
        return out


# ── LeanModuleFragmentedDetector ──────────────────────────────────────────────


@dataclass
class LeanModuleFragmentedDetector:
    """Flag Lean module roots whose nodes are spread across multiple blueprint roots.

    After scanning all nodes, groups nodes by the normalised Lean module root
    (first meaningful snake_case segment after stripping the project prefix).
    For each Lean root covering ≥ 2 nodes that span more than one blueprint
    root, emits a single ``info`` diagnostic.

    Suppression: if *all* nodes under that Lean root declare
    ``topic_lean_alignment: divergent``, the finding is suppressed.

    ``extra_aliases`` is merged on top of the built-in
    ``_BLUEPRINT_LEAN_ROOT_ALIASES`` table (extra wins on conflict). Use it
    to pass project-level ``lint.topic_lean_aliases`` from the config.
    """

    code: str = "LINT_LEAN_MODULE_FRAGMENTED"
    needs_llm: bool = False
    extra_aliases: dict[str, str] = field(default_factory=dict)

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        aliases = self.extra_aliases or None
        # Group nodes by lean_root → list of (blueprint_root, node_id, divergent)
        lean_root_map: dict[str, list[tuple[str, str, bool]]] = defaultdict(list)
        for node in nodes:
            if node.lean is None or not node.lean.modules:
                continue
            for module in node.lean.modules:
                lean_root = _lean_module_to_normalized_root(module, aliases)
                if lean_root is None:
                    continue
                home_topic = home_topic_for_node(node)
                blueprint_root = _canonical_root(home_topic.split(".")[0], aliases)
                is_divergent = node.topic_lean_alignment == "divergent"
                lean_root_map[lean_root].append((blueprint_root, node.id, is_divergent))

        out: list[Diagnostic] = []
        for lean_root in sorted(lean_root_map):
            entries = lean_root_map[lean_root]
            if len(entries) < 2:
                continue

            # Check suppression: all must be divergent
            if all(div for _, _, div in entries):
                continue

            # Group by blueprint root
            per_bp_root: dict[str, list[str]] = defaultdict(list)
            for bp_root, node_id, _ in entries:
                per_bp_root[bp_root].append(node_id)

            if len(per_bp_root) <= 1:
                continue

            # Build counts description
            counts_parts = ", ".join(
                f"{bp_root} ({len(nids)}): {', '.join(sorted(nids)[:3])}"
                + ("..." if len(nids) > 3 else "")
                for bp_root, nids in sorted(per_bp_root.items())
            )
            total = len(entries)
            out.append(Diagnostic(
                level="info",
                node_id="",
                message=(
                    f"Lean module root {lean_root!r} has {total} node(s) spread "
                    f"across {len(per_bp_root)} blueprint roots: {counts_parts}"
                ),
                code=self.code,
                related=(lean_root,),
            ))
        return out
