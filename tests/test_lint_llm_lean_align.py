"""Tests for LeanAlignmentLlmDetector.

Covers the 8-class alignment vocabulary mirrored from
:mod:`tools.knowledge.lean_alignment` (see README "MD-Lean Alignment
Verifier Contract"). Each label maps to a fixed lint severity.
"""
from __future__ import annotations

import json as _json_stdlib
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


def _classification_response(label: str, reason: str = "stub reason") -> str:
    return _json_stdlib.dumps({"classification": label, "reason": reason})


class TestPromptShape:
    def test_prompt_contains_node_statement_lean_signature_and_label_menu(self, tmp_path: Path):
        node = _node(
            "topic.thm",
            "Theorem",
            body="## Statement\nFor every group, the identity element is unique.\n",
            lean_decls=["Lib.proof_x"],
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", signature="theorem proof_x : ∀ g : Group, ...")])}
        runner = _FakeRunner(response=_classification_response("aligned"))
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        det.run([node], graph, llm=runner)
        assert len(runner.prompts) == 1
        prompt = runner.prompts[0]
        # Node + Lean inputs reach the prompt
        assert "topic.thm" in prompt
        assert "For every group, the identity element is unique." in prompt
        assert "theorem proof_x" in prompt
        # JSON-only output contract and the new schema keys
        assert "json" in prompt.lower()
        assert '"classification"' in prompt
        assert '"reason"' in prompt
        # All eight labels are listed verbatim
        for label in (
            "aligned",
            "lean_stronger",
            "lean_weaker",
            "lean_special_case",
            "lean_extra_hypotheses",
            "lean_missing_hypotheses",
            "definition_mismatch",
            "uncertain",
        ):
            assert label in prompt
        # Connects detector to the README contract by name so reviewers can
        # find the canonical decision vocabulary.
        assert "MD-Lean Alignment Verifier" in prompt


# --- Severity mapping ---------------------------------------------------------

_SILENT_LABELS = ("aligned", "lean_stronger")
_WARNING_LABELS = (
    "lean_weaker",
    "lean_special_case",
    "lean_extra_hypotheses",
    "lean_missing_hypotheses",
    "definition_mismatch",
)
_INFO_LABELS = ("uncertain",)


class TestSeverityMapping:
    @pytest.mark.parametrize("label", _SILENT_LABELS)
    def test_silent_labels_emit_nothing(self, tmp_path: Path, label: str):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response=_classification_response(label, reason="match"))
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []

    @pytest.mark.parametrize("label", _WARNING_LABELS)
    def test_warning_labels_emit_warning_with_related(self, tmp_path: Path, label: str):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(
            response=_classification_response(label, reason="explained mismatch")
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
        assert label in d.message
        assert "explained mismatch" in d.message

    @pytest.mark.parametrize("label", _INFO_LABELS)
    def test_info_labels_emit_info(self, tmp_path: Path, label: str):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(
            response=_classification_response(label, reason="not enough info")
        )
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"
        assert label in diags[0].message


class TestParsingFailures:
    def test_malformed_response_emits_one_info(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
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

    def test_missing_classification_key_treated_as_malformed(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        # Old binary schema is no longer accepted.
        runner = _FakeRunner(response='{"aligned": true}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"

    def test_unknown_label_treated_as_malformed(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response='{"classification": "mostly_aligned", "reason": "?"}')
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"
        # The unknown label leaks through as the raw payload in the
        # diagnostic message so a human can debug.
        assert "mostly_aligned" in diags[0].message


class TestPerronFrobeniusRegression:
    """Regression for the EconCSLib `perron_frobenius_positive_matrix.md`
    case: the Markdown ``## Statement`` carries a clause the Lean
    signature does not (\"the Loomis value provides λ = 1/v\"). Previously
    the binary detector returned ``aligned: true`` and the gap was
    missed; the multi-class detector classifies it as ``lean_weaker``
    and emits a single warning.
    """

    def test_md_stronger_than_lean_emits_warning(self, tmp_path: Path):
        node = _node(
            "linear_algebra.perron_frobenius_positive_matrix",
            "Perron-Frobenius For Positive Matrices",
            body=(
                "## Statement\n"
                "There exist x, y in the simplex and lambda > 0 with "
                "xM = lambda*x, My = lambda*y, both strictly positive. "
                "The Loomis value v of the pair (I, M) provides "
                "lambda = 1/v.\n"
            ),
            lean_decls=["EconCSLib.LinearAlgebra.perron_frobenius"],
        )
        graph, _ = build_graph([node])
        indexes = {
            "default": _index([
                _decl(
                    "EconCSLib.LinearAlgebra.perron_frobenius",
                    signature=(
                        "theorem perron_frobenius (M : Fin n -> Fin n -> Real) "
                        "(hM_pos : ...) : exists x y lam, 0 < lam ..."
                    ),
                )
            ])
        }
        runner = _FakeRunner(
            response=_classification_response(
                "lean_weaker",
                reason="Lean signature has no v and no claim that lam = 1/v.",
            )
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
        assert d.node_id == "linear_algebra.perron_frobenius_positive_matrix"
        assert d.related == ("EconCSLib.LinearAlgebra.perron_frobenius",)
        assert "lean_weaker" in d.message
        assert "lam = 1/v" in d.message


class TestResolutionPaths:
    def test_unresolved_declaration_is_skipped_silently(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.does_not_exist"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([])}  # empty
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        assert det.run([node], graph, llm=runner) == []
        assert runner.prompts == []

    def test_ambiguous_suffix_match_is_skipped_silently(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([
            _decl("Lib.A.proof_x"),
            _decl("Lib.B.proof_x"),
        ])}
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
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
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
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
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
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
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
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
        runner = _FakeRunner(response=_classification_response("aligned"))
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

        runner1 = _FakeRunner(response=_classification_response("lean_weaker", "mismatch"))
        det1 = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        det1.run([node], graph, llm=runner1)
        assert runner1.prompts

        runner2 = _FakeRunner(response=_classification_response("aligned", "should not be asked"))
        det2 = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            indexes=indexes,
        )
        diags = det2.run([node], graph, llm=runner2)
        assert runner2.prompts == []
        # Cached "lean_weaker" still produces the warning on the cold detector run.
        assert len(diags) == 1
        assert diags[0].level == "warning"
        assert "lean_weaker" in diags[0].message


class TestBudget:
    def test_zero_budget_emits_info_and_skips_llm(self, tmp_path: Path):
        node = _node("topic.thm", "Theorem", body="## Statement\nFoo.\n", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x")])}
        runner = _FakeRunner(response=_classification_response("lean_weaker"))
        det = LeanAlignmentLlmDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=0),
            indexes=indexes,
        )
        diags = det.run([node], graph, llm=runner)
        assert runner.prompts == []
        assert any(d.level == "info" and "budget" in d.message.lower() for d in diags)
        assert not any(d.level == "warning" for d in diags)
