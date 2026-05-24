# Blueprint Lint PR 7 — Detector 10 (statement ↔ Lean alignment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `LeanAlignmentLlmDetector` (code `LINT_LEAN_ALIGN`, `needs_llm=True`). For each node carrying a `lean.declarations` entry, resolve the entry against the per-repository `LeanIndex`, build a small JSON-friendly bundle of `(markdown statement, Lean signature + docstring + module + kind)`, ask the LLM whether the two describe the same theorem with `{"aligned": bool, "reason": str}`, cache the per-pair decision keyed by a hash of the bundle, and respect `--llm-budget`.

When `--llm` is unset, the detector is gated off by the existing `Linter.run` plumbing (same as `SemanticDupDetector`). When no LeanIndex is available (no Lean root configured / indexing failed for the relevant repo), the detector emits a single `info` "lean index not available; skipping LINT_LEAN_ALIGN" diagnostic and returns — mirroring `LeanRefKindDetector`.

**Architecture:** `LeanAlignmentLlmDetector` lives in `tools/knowledge/lint/_llm.py` next to `SemanticDupDetector`, sharing `_LintCache` / `_BudgetTracker` infrastructure from PR 6 and the `_resolve_declaration` helper from `_detectors.py`. The detector takes `cache`, `budget`, `indexes` constructor args; `_default_detectors(config, *, lean_indexes, cache, budget)` instantiates it alongside the others; `main()` already builds all three pieces (PR 5 + PR 6), so the only `main()` change is one new constructor call.

**Tech Stack:** Python 3.10+, stdlib (`hashlib`, `json`, `dataclasses`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 7 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PRs 1-6 plus two refactors (`lint.py` → package; `_detectors.py` → split with `_llm.py`) are on `main`. After the post-PR 6 split, the package is:

```
tools/knowledge/lint/
    __init__.py     # public re-exports
    _core.py        # Detector protocol, Linter, renderers, CLI, _default_detectors, main
    _cache.py       # _LintCache, _BudgetTracker, _content_hash
    _detectors.py   # 5 deterministic detectors (~373 lines)
    _llm.py         # SemanticDupDetector + helpers (~162 lines)
```

PR 7 appends one detector to `_llm.py`. Projected file size after the addition: ~290 lines (well under the per-file threshold).

The detector cannot reuse `tools.knowledge.lean_alignment.build_alignment_bundle` directly — that function spins up a fresh `KnowledgeContext` for every call, which is unacceptable for an N-call detector. Instead, the detector builds its own minimal bundle from `(node, LeanDeclaration)` using only data we already have: the node frontmatter + body, and the `LeanDeclaration.signature`/`docstring`/`module`/`kind` already populated by `index_lean_project`. The bundle shape is intentionally a small subset of the full alignment bundle — just enough to ask "do these describe the same theorem?".

Reusing `_resolve_declaration` from `_detectors.py` (exact match then unique suffix) keeps name-routing logic in one place. `_llm.py` already imports helpers from `_detectors`, so this is one more import.

## File Structure

- **Create**: none.
- **Modify**: `tools/knowledge/lint/_llm.py` — append `LeanAlignmentLlmDetector` + its prompt/cache-key/parse helpers + the `_PROMPT_VERSION_LEAN_ALIGN` constant.
- **Modify**: `tools/knowledge/lint/__init__.py` — re-export `LeanAlignmentLlmDetector`.
- **Modify**: `tools/knowledge/lint/_core.py` — `_default_detectors` instantiates the new detector with the already-threaded `lean_indexes`, `cache`, `budget`.
- **Create**: `tests/test_lint_llm_lean_align.py` — full TDD coverage with fake `LlmRunner` and hand-built `LeanIndex`.
- **Modify**: `tests/test_lint_orchestrator.py` — `TestDefaultDetectorsWiring` adds `LINT_LEAN_ALIGN` to the expected set.

---

### Task 1: `LeanAlignmentLlmDetector`

**Files:**
- Modify: `tools/knowledge/lint/_llm.py`
- Modify: `tools/knowledge/lint/__init__.py`
- Create: `tests/test_lint_llm_lean_align.py`

#### Step 1.1: Write the first failing tests

- [ ] Create `tests/test_lint_llm_lean_align.py`:

```python
"""Tests for LeanAlignmentLlmDetector (PR 7)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint import LeanAlignmentLlmDetector
from tools.knowledge.lint._cache import _BudgetTracker, _LintCache
from tools.knowledge.models import LeanRef, Node


@dataclass
class _FakeRunner:
    """LlmRunner stub that returns a fixed response and records prompts."""
    response: str
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _decl(
    qualified_name: str,
    *,
    kind: str = "theorem",
    signature: str = "theorem foo : True",
    docstring: str | None = None,
    module: str | None = "Lib.Mod",
) -> LeanDeclaration:
    return LeanDeclaration(
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        kind=kind,
        file=Path(f"{qualified_name.replace('.', '/')}.lean"),
        line=1,
        module=module,
        signature=signature,
        docstring=docstring,
    )


def _index(decls: list[LeanDeclaration]) -> LeanIndex:
    idx = LeanIndex()
    for d in decls:
        idx.declarations[d.qualified_name] = d
    return idx


def _node(node_id: str, title: str, *, kind: str = "theorem", body: str = "", lean_decls: list[str] | None = None) -> Node:
    return Node(
        id=node_id,
        title=title,
        kind=kind,
        status="formalized",
        body=body,
        lean=LeanRef(modules=["Lib.Mod"], declarations=list(lean_decls or [])),
    )


class TestPromptShape:
    def test_prompt_contains_node_statement_and_lean_signature(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFor every group, the identity element is unique.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", signature="theorem proof_x : ∀ g : Group, ...")])}
        runner = _FakeRunner(response='{"aligned": true, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        det.run([node], graph, llm=runner)
        assert len(runner.prompts) == 1
        prompt = runner.prompts[0]
        assert "topic.thm" in prompt
        assert "For every group, the identity element is unique." in prompt
        assert "theorem proof_x" in prompt
        assert "json" in prompt.lower()
        assert '"aligned"' in prompt
        assert '"reason"' in prompt


class TestDecisionPaths:
    def test_aligned_true_emits_no_warning(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"aligned": true, "reason": "match"}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []

    def test_aligned_false_emits_warning_with_related(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(
            response='{"aligned": false, "reason": "Lean signature does not constrain g."}'
        )
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_LEAN_ALIGN"
        assert d.node_id == "topic.thm"
        assert d.related == ("Lib.proof_x",)
        assert "Lean signature does not constrain g." in d.message

    def test_malformed_response_emits_one_info(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response="not json")
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"
        assert "parse" in diags[0].message.lower() or "json" in diags[0].message.lower()

    def test_missing_aligned_key_treated_as_malformed(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"verdict": "yes"}')  # wrong key
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"


class TestResolutionPaths:
    def test_unresolved_declaration_is_skipped_silently(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["Lib.does_not_exist"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([])}  # empty
        runner = _FakeRunner(response='{"aligned": false, "reason": "should not be asked"}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []
        assert runner.prompts == []

    def test_ambiguous_suffix_match_is_skipped_silently(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFoo.\n",
            lean_decls=["proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([
            _decl("Lib.A.proof_x"),
            _decl("Lib.B.proof_x"),
        ])}
        runner = _FakeRunner(response='{"aligned": false, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []
        assert runner.prompts == []

    def test_explicit_repository_routing(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        node = Node(
            id=node.id,
            title=node.title,
            kind=node.kind,
            status=node.status,
            body=node.body,
            lean=LeanRef(repository="external", modules=node.lean.modules, declarations=node.lean.declarations),
        )
        graph, _ = build_graph([node])
        indexes = {
            "default": _index([_decl("Lib.proof_x", signature="default-signature")]),
            "external": _index([_decl("Lib.proof_x", signature="external-signature")]),
        }
        runner = _FakeRunner(response='{"aligned": false, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        det.run([node], graph, llm=runner)
        assert len(runner.prompts) == 1
        assert "external-signature" in runner.prompts[0]
        assert "default-signature" not in runner.prompts[0]


class TestKindFilter:
    def test_proof_plan_kind_is_skipped(self, tmp_path: Path):
        thm = _node("topic.thm", "Theorem")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
            body="## Statement\nplan body\n",
            lean=LeanRef(modules=[], declarations=["Lib.proof_x"]),
        )
        graph, _ = build_graph([thm, plan])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"aligned": false, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        # Proof plans don't carry a first-class Lean statement claim; skip them.
        assert det.run([thm, plan], graph, llm=runner) == []
        assert runner.prompts == []

    def test_node_without_lean_section_is_skipped(self, tmp_path: Path):
        node = Node(id="topic.thm", title="Theorem", kind="theorem", status="formalized", body="## Statement\n...\n")
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"aligned": false, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []
        assert runner.prompts == []


class TestNoLeanIndex:
    def test_none_indexes_emit_single_info(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        runner = _FakeRunner(response='{"aligned": true, "reason": "..."}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=None,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"
        assert "lean index not available" in diags[0].message.lower()
        assert runner.prompts == []


class TestCaching:
    def test_second_run_with_same_inputs_does_not_call_llm(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}

        runner1 = _FakeRunner(response='{"aligned": false, "reason": "mismatch"}')
        det1 = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        det1.run([node], graph, llm=runner1)
        assert runner1.prompts

        runner2 = _FakeRunner(response='{"aligned": true, "reason": "should not be asked"}')
        det2 = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det2.run([node], graph, llm=runner2)
        assert runner2.prompts == []
        # Cached "aligned: false" still produces the warning on the cold detector run.
        assert len(diags) == 1
        assert diags[0].level == "warning"


class TestBudget:
    def test_zero_budget_emits_info_and_skips_llm(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"aligned": false, "reason": "should not be asked"}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=0),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert runner.prompts == []
        assert any(d.level == "info" and "budget" in d.message.lower() for d in diags)
        assert not any(d.level == "warning" for d in diags)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_llm_lean_align.py -q`
- [ ] Expected: `ImportError: cannot import name 'LeanAlignmentLlmDetector'`.

#### Step 1.2: Implement the detector

Append to `tools/knowledge/lint/_llm.py`:

```python
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint._detectors import _resolve_declaration

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
_ELIGIBLE_KINDS_FOR_ALIGN = _THEOREM_LIKE_KINDS_FOR_ALIGN | _DEFINITION_LIKE_KINDS_FOR_ALIGN


def _lean_align_prompt(node: Node, decl_name: str, decl: LeanDeclaration) -> str:
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

        default_index = self.indexes.get("default") or next(iter(self.indexes.values()), None)
        out: list[Diagnostic] = []
        budget_already_reported = False

        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            if node.kind not in _ELIGIBLE_KINDS_FOR_ALIGN:
                continue
            if node.lean is None or not node.lean.declarations:
                continue
            repo_id = node.lean.repository
            index = self.indexes.get(repo_id) if repo_id is not None else default_index
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
```

#### Step 1.3: Re-export

- [ ] Add `LeanAlignmentLlmDetector` to the `from tools.knowledge.lint._llm import ...` line in `tools/knowledge/lint/__init__.py` and to `__all__`.

#### Step 1.4: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_llm_lean_align.py -q`
- [ ] Expected: every test passes. No real `claude` subprocess is invoked.

#### Step 1.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: 632 + ~14 = ~646 passing.

#### Step 1.6: Commit Task 1

```bash
git add tools/knowledge/lint/_llm.py tools/knowledge/lint/__init__.py tests/test_lint_llm_lean_align.py
git commit -m "$(cat <<'EOF'
feat(lint): add LeanAlignmentLlmDetector (LINT_LEAN_ALIGN)

For each theorem-like or definition-like node carrying a
lean.declarations entry that resolves through the injected LeanIndex,
build a JSON-prompt that includes the node statement, the resolved
Lean signature, docstring, kind, and module, and ask the LlmRunner
whether the two describe the same theorem. Decisions are content-
hashed into _LintCache (prompt-version v1) so repeated runs reuse
prior judgements; the per-run _BudgetTracker caps total LLM calls.

Skipped silently: proof-plan / task / topic / example kinds, nodes
with no lean section, declarations that fail to resolve (exact or
unique suffix). When no LeanIndex is available the detector emits
one info diagnostic and returns; gating via Linter.run keeps the
detector quiet when --llm is unset. Issue #121, PR 7.
EOF
)"
```

---

### Task 2: Wire `LeanAlignmentLlmDetector` into `_default_detectors`

**Files:**
- Modify: `tools/knowledge/lint/_core.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 2.1: Update `TestDefaultDetectorsWiring`

In `tests/test_lint_orchestrator.py`:

```python
class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            LeanAlignmentLlmDetector,
            LeanRefKindDetector,
            SemanticDupDetector,
            StagedAdmittedOverlapDetector,
            _default_detectors,
        )

        detectors = _default_detectors(
            LintConfig(fuzzy_threshold=0.77, semantic_candidate_threshold=0.6),
        )
        codes = {d.code for d in detectors}
        assert codes >= {
            "LINT_FUZZY_DUP",
            "LINT_STAGED_OVERLAP",
            "LINT_REDUNDANT_DEP",
            "LINT_ORPHAN",
            "LINT_LEAN_KIND",
            "LINT_SEMANTIC_DUP",
            "LINT_LEAN_ALIGN",
        }

        align = next(d for d in detectors if isinstance(d, LeanAlignmentLlmDetector))
        # Without an explicit lean_indexes kwarg it falls back to None
        # and will emit a single info when run.
        assert align.indexes is None
```

#### Step 2.2: Update `_default_detectors`

In `tools/knowledge/lint/_core.py`, append the new detector to the returned list:

```python
def _default_detectors(
    config: "LintConfig | None" = None,
    *,
    lean_indexes: "dict[str, LeanIndex] | None" = None,
    cache: "_LintCache | None" = None,
    budget: "_BudgetTracker | None" = None,
) -> list[Detector]:
    from tools.knowledge.config import LintConfig as _LintConfig
    from tools.knowledge.lint._cache import _BudgetTracker as _BT, _LintCache as _LC
    from tools.knowledge.lint._llm import LeanAlignmentLlmDetector, SemanticDupDetector
    cfg = config if config is not None else _LintConfig()
    cache = cache if cache is not None else _LC(cache_dir=None)
    budget = budget if budget is not None else _BT(budget=None)
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
        LeanRefKindDetector(indexes=lean_indexes),
        SemanticDupDetector(
            cache=cache,
            budget=budget,
            candidate_threshold=cfg.semantic_candidate_threshold,
        ),
        LeanAlignmentLlmDetector(
            cache=cache,
            budget=budget,
            indexes=lean_indexes,
        ),
    ]
```

#### Step 2.3: Smoke

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: Same output as PR 6 (2 LINT_REDUNDANT_DEP + 1 LINT_LEAN_KIND info). The new detector is `needs_llm=True` so it stays gated off without `--llm`. Exit 0.

#### Step 2.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 2.5: `mdblueprint-check` byte-identical

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output.

#### Step 2.6: Commit Task 2

```bash
git add tools/knowledge/lint/_core.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): wire LeanAlignmentLlmDetector into _default_detectors

main() already builds lean_indexes (PR 5) and the cache + budget
(PR 6), so this PR only needs to add one more detector instance to
the default list with those same kwargs threaded in. The detector
stays gated off without --llm via the existing Linter.run plumbing;
bundled-example smoke output is unchanged. Issue #121, PR 7.
EOF
)"
```

---

## Definition of Done

- [ ] `tools/knowledge/lint/_llm.py` defines `LeanAlignmentLlmDetector` with `code="LINT_LEAN_ALIGN"`, `needs_llm=True`, and constructor args `cache`, `budget`, `indexes`.
- [ ] `_lean_align_prompt`, `_lean_align_cache_key`, `_parse_lean_align_response`, and `_PROMPT_VERSION_LEAN_ALIGN` live alongside the detector.
- [ ] Reuses `_resolve_declaration` from `_detectors.py` (no duplicated name-routing logic).
- [ ] `_default_detectors(config, *, lean_indexes, cache, budget)` instantiates the detector with the threaded `cache`, `budget`, and `lean_indexes`.
- [ ] `tests/test_lint_llm_lean_align.py` covers: prompt shape, all three decision paths (aligned / misaligned / malformed), unresolved name, ambiguous suffix, explicit repository routing, proof-plan skip, no-lean-section skip, no-index info, cache reuse, and budget enforcement.
- [ ] `tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring` asserts on the seven-code set.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0 with the same output as PR 6 (detector gated off without `--llm`).
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` byte-identical.
- [ ] Two commits on `main`, no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint/_llm.py` stays under 400 lines.
- [ ] No real `claude` subprocess is spawned anywhere in the test suite.

## Hand-off to PR 8

PR 8 is documentation + the `#127` follow-on detector (`PlanCompletedButStatusNotPromoted`, `LINT_PLAN_PROMOTE`). New rule docs in `docs/lint.md`, `mdblueprint-lint` row in `AGENTS.md`'s focused-check table, plus the `proved_via_plan`-aware detector that pairs with `tools/knowledge/promote_via_plan.py` (the workflow companion shipped in #128).
