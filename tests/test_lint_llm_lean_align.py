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
