"""Tests for PlanPromoteDetector (PR 8 / closes #127)."""
from __future__ import annotations

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import PlanPromoteDetector
from tools.knowledge.models import LeanRef, Node


def _node(node_id: str, *, kind: str = "theorem", status: str = "formalized",
          uses: list[str] | None = None, proved_via_plan: str | None = None,
          lean: LeanRef | None = None) -> Node:
    kwargs: dict = {
        "id": node_id,
        "title": node_id,
        "kind": kind,
        "status": status,
        "uses": list(uses or []),
    }
    if proved_via_plan is not None:
        kwargs["proved_via_plan"] = proved_via_plan
    if lean is not None:
        kwargs["lean"] = lean
    return Node(**kwargs)


class TestEmitsOnce:
    def test_theorem_with_ready_plan_and_unpromoted_status_is_flagged(self):
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])

        det = PlanPromoteDetector()
        diags = det.run([base, plan, thm], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"  # default severity
        assert d.code == "LINT_PLAN_PROMOTE"
        assert d.node_id == "topic.thm"
        # related names the plan that supplies the proof.
        assert d.related == ("topic.thm.plan.direct",)
        # Message mentions both endpoints and the canonical fix.
        assert "topic.thm" in d.message
        assert "topic.thm.plan.direct" in d.message
        assert "promote" in d.message.lower() or "proved_via_plan" in d.message.lower()


class TestSeverity:
    def test_severity_warning_promotes_diagnostic_level(self):
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])

        det = PlanPromoteDetector(severity="warning")
        diags = det.run([base, plan, thm], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "warning"

    def test_severity_other_values_rejected_at_construction(self):
        with pytest.raises(ValueError):
            PlanPromoteDetector(severity="shout")


class TestSilentPaths:
    def test_already_proved_theorem_is_silent(self):
        # status: proved means the author has already done the promotion;
        # the detector should not nag.
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node(
            "topic.thm", kind="theorem", status="proved",
            proved_via_plan="topic.thm.plan.direct",
            lean=LeanRef(modules=["Lib.Mod"], declarations=["Lib.thm"]),
        )
        graph, _ = build_graph([base, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, plan, thm], graph, llm=None) == []

    def test_plan_not_yet_ready_is_silent(self):
        # The plan exists but is staged — nothing to promote yet.
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.draft",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, plan, thm], graph, llm=None) == []

    def test_plan_ancestor_not_ready_is_silent(self):
        # Plan itself is formalized, but it transitively depends on an
        # admitted lemma whose own proof is not in Lean — plan does not
        # actually supply a complete proof.
        base = _node("topic.base", kind="definition", status="formalized")
        intermediate = _node(
            "topic.intermediate", kind="lemma", status="admitted",
            uses=["topic.base"],
        )
        plan = Node(
            id="topic.thm.plan.via_intermediate",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.intermediate"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, intermediate, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, intermediate, plan, thm], graph, llm=None) == []

    def test_theorem_with_no_attached_plan_is_silent(self):
        # No plans at all — the detector has nothing to nudge about.
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([thm])
        det = PlanPromoteDetector()
        assert det.run([thm], graph, llm=None) == []

    def test_non_theorem_kind_is_skipped(self):
        # Only theorem-like nodes can carry proved_via_plan markers.
        defn = _node("topic.x", kind="definition", status="formalized")
        graph, _ = build_graph([defn])
        det = PlanPromoteDetector()
        assert det.run([defn], graph, llm=None) == []


class TestMultiplePlans:
    def test_prefers_selected_plan_in_related(self):
        # Two qualifying plans; the diagnostic should name the selected one
        # so authors who run `promote_via_plan` get a consistent answer.
        base = _node("topic.base", kind="definition", status="formalized")
        candidate = Node(
            id="topic.thm.plan.alpha",
            title="Alpha",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="candidate",
            uses=["topic.base"],
        )
        selected = Node(
            id="topic.thm.plan.beta",
            title="Beta",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, candidate, selected, thm])
        det = PlanPromoteDetector()
        diags = det.run([base, candidate, selected, thm], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].related == ("topic.thm.plan.beta",)
