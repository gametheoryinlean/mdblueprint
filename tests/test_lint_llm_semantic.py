"""Tests for SemanticDupDetector (PR 6)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import SemanticDupDetector
from tools.knowledge.lint._cache import _BudgetTracker, _LintCache
from tools.knowledge.models import Node


@dataclass
class _FakeRunner:
    """LlmRunner that returns a fixed response and records every prompt."""
    response: str
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _node(node_id: str, title: str, *, status: str = "admitted", body: str = "") -> Node:
    return Node(id=node_id, title=title, kind="theorem", status=status, body=body)


def _pair_near_fuzzy_threshold() -> tuple[Node, Node]:
    # ~0.86 similarity in titles — above semantic_candidate_threshold=0.75
    # but below fuzzy_threshold=0.92.
    a = _node("alg.x", "Identity element of a group is unique")
    b = _node("alg.y", "The identity element of a group is unique element")
    return a, b


class TestPromptShape:
    def test_prompt_contains_both_statements_and_json_instruction(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "different"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        det.run([a, b], graph, llm=runner)
        assert len(runner.prompts) == 1
        prompt = runner.prompts[0]
        assert "alg.x" in prompt
        assert "alg.y" in prompt
        assert a.title in prompt
        assert b.title in prompt
        # The prompt must ask for JSON specifically so parsing is deterministic.
        assert "json" in prompt.lower()
        # And it should name the expected keys.
        assert '"same"' in prompt
        assert '"reason"' in prompt


class TestDecisionPaths:
    def test_same_true_emits_warning_with_related(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(
            response='{"same": true, "reason": "Both state uniqueness of the identity."}'
        )
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_SEMANTIC_DUP"
        # Source node is the lex-smaller of the pair; related is the other.
        assert d.node_id == "alg.x"
        assert d.related == ("alg.y",)
        # Message echoes the model's reason for traceability.
        assert "uniqueness of the identity" in d.message.lower()

    def test_same_false_emits_no_warning(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "different facts"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []

    def test_malformed_response_emits_one_info(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response="not valid json at all")
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"
        assert d.code == "LINT_SEMANTIC_DUP"
        assert "parse" in d.message.lower() or "json" in d.message.lower()

    def test_missing_same_key_treated_as_malformed(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"answer": "yes"}')  # wrong key
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"


class TestCandidateSelection:
    def test_pair_below_candidate_threshold_is_not_judged(self, tmp_path: Path):
        a = _node("alg.x", "Group identity is unique")
        b = _node("ana.z", "Cauchy-Schwarz inequality")  # very different
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "should not be asked"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []
        assert runner.prompts == []

    def test_only_admitted_nodes_are_candidates(self, tmp_path: Path):
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity element of a group is unique element", status="staged")
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []
        assert runner.prompts == []


class TestCaching:
    def test_second_run_with_same_inputs_does_not_call_llm(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner1 = _FakeRunner(response='{"same": true, "reason": "Same."}')
        cache = _LintCache(tmp_path)
        det1 = SemanticDupDetector(
            cache=cache, budget=_BudgetTracker(budget=10), candidate_threshold=0.75,
        )
        det1.run([a, b], graph, llm=runner1)
        assert runner1.prompts  # first run did call

        # Fresh runner; same cache directory.
        runner2 = _FakeRunner(response='{"same": false, "reason": "should not be asked"}')
        det2 = SemanticDupDetector(
            cache=_LintCache(tmp_path),  # cold instance, warm on-disk cache
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det2.run([a, b], graph, llm=runner2)
        # Cache hit: zero new LLM calls, but the warning is still produced from
        # the cached `same: true` decision.
        assert runner2.prompts == []
        assert len(diags) == 1
        assert diags[0].level == "warning"

    def test_no_cache_mode_still_dedupes_within_a_run(self, tmp_path: Path):
        # A second identical pair in the same run should reuse the cached
        # answer from the first call even with cache_dir=None.
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity element of a group is unique element")
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(cache_dir=None),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        # Two consecutive runs against the same fixture; expect one LLM call.
        det.run([a, b], graph, llm=runner)
        det.run([a, b], graph, llm=runner)
        assert len(runner.prompts) == 1


class TestBudget:
    def test_zero_budget_emits_info_and_skips_llm(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "should not be called"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=0),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert runner.prompts == []
        # One info "budget exhausted" diagnostic; no warnings.
        assert any(d.level == "info" and "budget" in d.message.lower() for d in diags)
        assert not any(d.level == "warning" for d in diags)

    def test_budget_one_calls_at_most_once_across_many_candidates(self, tmp_path: Path):
        nodes: list[Node] = []
        for i in range(4):
            nodes.append(_node(f"alg.x{i}", f"Identity element of a group is unique variant {i}"))
            nodes.append(_node(f"alg.y{i}", f"The identity element of a group is unique element variant {i}"))
        graph, _ = build_graph(nodes)
        runner = _FakeRunner(response='{"same": true, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=1),
            candidate_threshold=0.75,
        )
        det.run(nodes, graph, llm=runner)
        assert len(runner.prompts) == 1
