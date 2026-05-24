"""Built-in lint detectors and their private string/graph-walk helpers."""
from __future__ import annotations

import json as _json_stdlib
import re
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint._cache import _BudgetTracker, _LintCache, _content_hash
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


# ── Semantic duplicate detector (LLM-backed) ──────────────────────────────────

_PROMPT_VERSION_SEMANTIC_DUP = "v1"
_BUDGET_INFO_MESSAGE = (
    "LLM budget exhausted; skipped remaining LINT_SEMANTIC_DUP candidates"
)


def _semantic_dup_prompt(a: Node, b: Node) -> str:
    """Build the per-pair prompt.

    The exact text is part of the cache key via
    ``_PROMPT_VERSION_SEMANTIC_DUP``, so any wording change should bump the
    version constant to invalidate prior cached judgements.
    """
    a_stmt = _statement_text(a) or a.body or ""
    b_stmt = _statement_text(b) or b.body or ""
    return (
        "Two mathematical knowledge-base nodes are below. Decide whether they "
        "state the same mathematical claim (allowing renaming and notational "
        "differences). Reply with a single JSON object of the form "
        '{"same": <bool>, "reason": "<one-sentence justification>"}.\n\n'
        f"Node 1 id: {a.id}\nTitle: {a.title}\nStatement:\n{a_stmt}\n\n"
        f"Node 2 id: {b.id}\nTitle: {b.title}\nStatement:\n{b_stmt}\n\n"
        "Return only the JSON object."
    )


def _semantic_dup_cache_key(a: Node, b: Node) -> str:
    body = "\n".join([
        _PROMPT_VERSION_SEMANTIC_DUP,
        a.id, a.title, _statement_text(a) or a.body or "",
        b.id, b.title, _statement_text(b) or b.body or "",
    ])
    return _content_hash(body)


def _parse_semantic_dup_response(raw: str) -> tuple[bool | None, str]:
    """Return ``(same | None on parse failure, reason)``."""
    try:
        payload = _json_stdlib.loads(raw)
    except Exception:
        return None, raw[:200]
    if not isinstance(payload, dict) or "same" not in payload:
        return None, raw[:200]
    same = payload.get("same")
    if not isinstance(same, bool):
        return None, raw[:200]
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    return same, reason


@dataclass
class SemanticDupDetector:
    """Ask an LLM whether candidate near-duplicate pairs really state the same theorem."""

    cache: _LintCache
    budget: _BudgetTracker
    candidate_threshold: float = 0.75
    code: str = "LINT_SEMANTIC_DUP"
    needs_llm: bool = True

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        if llm is None:
            return []

        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        # Candidate pair set: (a, b) with a.id < b.id and fuzzy ratio
        # >= candidate_threshold (titles, with statement fallback).
        candidates: list[tuple[float, Node, Node]] = []
        for index, a in enumerate(admitted):
            a_title = _normalize(a.title)
            a_stmt = _normalize(_statement_text(a))
            for b in admitted[index + 1:]:
                b_title = _normalize(b.title)
                score = _ratio(a_title, b_title)
                if score < self.candidate_threshold:
                    b_stmt = _normalize(_statement_text(b))
                    if a_stmt and b_stmt:
                        score = max(score, _ratio(a_stmt, b_stmt))
                if score >= self.candidate_threshold:
                    candidates.append((score, a, b))

        # Deterministic order: highest ratio first, ties by sorted ids.
        candidates.sort(key=lambda triple: (-triple[0], triple[1].id, triple[2].id))

        out: list[Diagnostic] = []
        budget_already_reported = False
        for _, a, b in candidates:
            key = _semantic_dup_cache_key(a, b)
            cached = self.cache.get(self.code, key)
            if cached is None:
                if not self.budget.try_spend():
                    if not budget_already_reported:
                        out.append(Diagnostic(
                            level="info",
                            node_id="",
                            message=_BUDGET_INFO_MESSAGE,
                            code=self.code,
                        ))
                        budget_already_reported = True
                    break
                raw = llm(_semantic_dup_prompt(a, b))
                same, reason = _parse_semantic_dup_response(raw)
                cached = {"same": same, "reason": reason, "raw": raw[:2000]}
                self.cache.put(self.code, key, cached)

            same = cached.get("same")
            reason = cached.get("reason", "")
            if same is None:
                out.append(Diagnostic(
                    level="info",
                    node_id=a.id,
                    message=(
                        f"could not parse JSON from LLM response for semantic-dup "
                        f"judgement of {a.id!r} vs {b.id!r}; raw: {reason}"
                    ),
                    file_path=a.file_path,
                    code=self.code,
                    related=(b.id,),
                ))
                continue
            if same:
                out.append(Diagnostic(
                    level="warning",
                    node_id=a.id,
                    message=(
                        f"LLM judged {a.id!r} and {b.id!r} as the same theorem: {reason}"
                    ),
                    file_path=a.file_path,
                    code=self.code,
                    related=(b.id,),
                ))
        return out
