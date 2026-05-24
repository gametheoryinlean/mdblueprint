"""LLM-backed lint detectors and their prompt/cache-key helpers."""
from __future__ import annotations

import json as _json_stdlib
from dataclasses import dataclass
from typing import Callable

from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint._cache import _BudgetTracker, _LintCache, _content_hash
from tools.knowledge.lint._detectors import (
    _normalize,
    _ratio,
    _resolve_declaration,
    _statement_text,
)
from tools.knowledge.models import ADMITTED_STATUSES, Node
from tools.knowledge.validator import Diagnostic

LlmRunner = Callable[[str], str]

# ── Semantic duplicate detector constants and helpers ─────────────────────────

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


# ── SemanticDupDetector ───────────────────────────────────────────────────────

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


# ── Lean alignment detector constants and helpers ─────────────────────────────

_PROMPT_VERSION_LEAN_ALIGN = "v1"
_BUDGET_INFO_MESSAGE_LEAN_ALIGN = (
    "LLM budget exhausted; skipped remaining LINT_LEAN_ALIGN candidates"
)
_NO_INDEX_INFO_MESSAGE_LEAN_ALIGN = (
    "lean index not available; skipping LINT_LEAN_ALIGN"
)

_THEOREM_LIKE_KINDS_FOR_ALIGN = frozenset(
    {"lemma", "proposition", "theorem", "external-theorem"}
)
_DEFINITION_LIKE_KINDS_FOR_ALIGN = frozenset({"definition", "concept"})
_ELIGIBLE_KINDS_FOR_ALIGN = (
    _THEOREM_LIKE_KINDS_FOR_ALIGN | _DEFINITION_LIKE_KINDS_FOR_ALIGN
)


def _lean_align_prompt(node: Node, decl_name: str, decl: LeanDeclaration) -> str:
    """Build the per-pair prompt for the Lean alignment detector.

    The exact text is part of the cache key via
    ``_PROMPT_VERSION_LEAN_ALIGN``, so any wording change should bump the
    version constant to invalidate prior cached judgements.
    """
    statement = _statement_text(node) or node.body or ""
    signature = decl.signature or ""
    docstring = decl.docstring or ""
    module = decl.module or ""
    return (
        "You are checking whether a Markdown knowledge-base node and its "
        "claimed Lean declaration describe the same theorem or definition.\n\n"
        f"Markdown node id: {node.id}\n"
        f"Title: {node.title}\n"
        f"Kind: {node.kind}\n"
        f"Statement:\n{statement}\n\n"
        f"Lean declaration: {decl_name}\n"
        f"Qualified name: {decl.qualified_name}\n"
        f"Lean kind: {decl.kind}\n"
        f"Module: {module}\n"
        f"Signature:\n{signature}\n"
        f"Docstring:\n{docstring}\n\n"
        "Reply with a single JSON object of the form "
        '{"aligned": <bool>, "reason": "<one-sentence justification>"}.\n'
        "Return only the JSON object."
    )


def _lean_align_cache_key(node: Node, decl_name: str, decl: LeanDeclaration) -> str:
    body = "\n".join([
        _PROMPT_VERSION_LEAN_ALIGN,
        node.id, node.title, node.kind,
        _statement_text(node) or node.body or "",
        decl_name, decl.qualified_name, decl.kind,
        decl.module or "", decl.signature or "", decl.docstring or "",
    ])
    return _content_hash(body)


def _parse_lean_align_response(raw: str) -> tuple[bool | None, str]:
    """Return ``(aligned | None on parse failure, reason)``."""
    try:
        payload = _json_stdlib.loads(raw)
    except Exception:
        return None, raw[:200]
    if not isinstance(payload, dict) or "aligned" not in payload:
        return None, raw[:200]
    aligned = payload.get("aligned")
    if not isinstance(aligned, bool):
        return None, raw[:200]
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    return aligned, reason


# ── LeanAlignmentLlmDetector ──────────────────────────────────────────────────

@dataclass
class LeanAlignmentLlmDetector:
    """Ask an LLM whether each (node, Lean declaration) pair really aligns."""

    cache: _LintCache
    budget: _BudgetTracker
    indexes: dict[str, LeanIndex] | None = None
    code: str = "LINT_LEAN_ALIGN"
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
        if not self.indexes:
            return [Diagnostic(
                level="info",
                node_id="",
                message=_NO_INDEX_INFO_MESSAGE_LEAN_ALIGN,
                code=self.code,
            )]

        default_index = self.indexes.get("default") or next(
            iter(self.indexes.values()), None
        )
        out: list[Diagnostic] = []
        budget_already_reported = False

        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            if node.kind not in _ELIGIBLE_KINDS_FOR_ALIGN:
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

                key = _lean_align_cache_key(node, decl_name, resolved)
                cached = self.cache.get(self.code, key)
                if cached is None:
                    if not self.budget.try_spend():
                        if not budget_already_reported:
                            out.append(Diagnostic(
                                level="info",
                                node_id="",
                                message=_BUDGET_INFO_MESSAGE_LEAN_ALIGN,
                                code=self.code,
                            ))
                            budget_already_reported = True
                        return out
                    raw = llm(_lean_align_prompt(node, decl_name, resolved))
                    aligned, reason = _parse_lean_align_response(raw)
                    cached = {"aligned": aligned, "reason": reason, "raw": raw[:2000]}
                    self.cache.put(self.code, key, cached)

                aligned = cached.get("aligned")
                reason = cached.get("reason", "")
                if aligned is None:
                    out.append(Diagnostic(
                        level="info",
                        node_id=node.id,
                        message=(
                            f"could not parse JSON from LLM response for Lean alignment "
                            f"of {node.id!r} vs {decl_name!r}; raw: {reason}"
                        ),
                        file_path=node.file_path,
                        code=self.code,
                        related=(decl_name,),
                    ))
                    continue
                if aligned is False:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=node.id,
                        message=(
                            f"LLM judged {node.id!r} and Lean declaration {decl_name!r} "
                            f"as misaligned: {reason}"
                        ),
                        file_path=node.file_path,
                        code=self.code,
                        related=(decl_name,),
                    ))
        return out
