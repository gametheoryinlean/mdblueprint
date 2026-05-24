"""Tests for HierarchyInversionDetector and TopicCycleDetector (closes #137 / #138)."""
from __future__ import annotations

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import (
    HierarchyInversionDetector,
    TopicCycleDetector,
)
from tools.knowledge.models import Node


def _node(
    node_id: str,
    *,
    kind: str = "theorem",
    status: str = "admitted",
    primary_topic: str | None = None,
    uses: list[str] | None = None,
) -> Node:
    kwargs: dict = {
        "id": node_id,
        "title": node_id,
        "kind": kind,
        "status": status,
        "uses": list(uses or []),
    }
    if primary_topic is not None:
        kwargs["primary_topic"] = primary_topic
    return Node(**kwargs)


class TestHierarchyInversionDetector:
    def test_emits_warning_when_parent_depends_on_subtopic(self):
        # Subtopic prereq, parent-tagged dependent. Hierarchy inversion.
        prereq = _node("alg.cohomology.cup_product", kind="definition")
        dependent = _node(
            "alg.headline",
            kind="theorem",
            primary_topic="alg",  # parent topic
            uses=["alg.cohomology.cup_product"],
        )
        graph, _ = build_graph([prereq, dependent])
        det = HierarchyInversionDetector()
        diags = det.run([prereq, dependent], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_HIERARCHY_INVERSION"
        assert d.node_id == "alg.headline"
        assert d.related == ("alg.cohomology.cup_product",)
        assert "alg.cohomology" in d.message
        assert "alg.headline" in d.message

    def test_subtopic_depending_on_parent_is_silent(self):
        # This is the HEALTHY direction (child relies on parent's basics).
        parent_node = _node("alg.group", kind="definition")
        child_node = _node(
            "alg.cohomology.complex",
            kind="definition",
            uses=["alg.group"],
        )
        graph, _ = build_graph([parent_node, child_node])
        det = HierarchyInversionDetector()
        assert det.run([parent_node, child_node], graph, llm=None) == []

    def test_cross_sibling_subtopic_is_silent(self):
        # Sibling subtopic dependencies are not hierarchy inversions; they
        # may or may not be desirable but are TopicCycleDetector's province.
        a = _node("alg.groups.identity_unique", kind="theorem")
        b = _node(
            "alg.rings.identity_unique",
            kind="theorem",
            uses=["alg.groups.identity_unique"],
        )
        graph, _ = build_graph([a, b])
        det = HierarchyInversionDetector()
        assert det.run([a, b], graph, llm=None) == []

    def test_same_topic_is_silent(self):
        a = _node("alg.x", kind="definition")
        b = _node("alg.y", kind="theorem", uses=["alg.x"])
        graph, _ = build_graph([a, b])
        det = HierarchyInversionDetector()
        assert det.run([a, b], graph, llm=None) == []

    def test_severity_can_be_demoted_to_info(self):
        prereq = _node("alg.cohomology.cup_product", kind="definition")
        dependent = _node(
            "alg.headline",
            kind="theorem",
            primary_topic="alg",
            uses=["alg.cohomology.cup_product"],
        )
        graph, _ = build_graph([prereq, dependent])
        det = HierarchyInversionDetector(severity="info")
        diags = det.run([prereq, dependent], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "info"

    def test_invalid_severity_rejected_at_construction(self):
        with pytest.raises(ValueError):
            HierarchyInversionDetector(severity="shout")

    def test_deep_descendant_still_triggers(self):
        # alg vs alg.x.y.z — descend two levels deep, still an inversion.
        deep = _node("alg.x.y.z", kind="definition")
        shallow = _node(
            "alg.headline",
            kind="theorem",
            primary_topic="alg",
            uses=["alg.x.y.z"],
        )
        graph, _ = build_graph([deep, shallow])
        det = HierarchyInversionDetector()
        diags = det.run([deep, shallow], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].related == ("alg.x.y.z",)


class TestTopicCycleDetector:
    def test_emits_info_for_sibling_cycle(self):
        # alg.x ↔ alg.y at child-topic level
        # alg.x.a depends on alg.y.b; alg.y.c depends on alg.x.d
        a = _node("alg.x.a", kind="definition")
        b = _node("alg.y.b", kind="definition")
        c = _node("alg.y.c", kind="theorem", uses=["alg.x.a"])
        d = _node("alg.x.d", kind="theorem", uses=["alg.y.b"])
        graph, _ = build_graph([a, b, c, d])
        det = TopicCycleDetector()
        diags = det.run([a, b, c, d], graph, llm=None)
        assert len(diags) == 1
        d_diag = diags[0]
        assert d_diag.level == "info"
        assert d_diag.code == "LINT_TOPIC_CYCLE"
        assert "alg.x" in d_diag.message
        assert "alg.y" in d_diag.message
        assert "alg" in d_diag.message  # parent topic named in message

    def test_silent_when_no_back_edge(self):
        # alg.x.a → alg.y.b only, no return edge.
        a = _node("alg.x.a", kind="definition")
        b = _node("alg.y.b", kind="theorem", uses=["alg.x.a"])
        graph, _ = build_graph([a, b])
        det = TopicCycleDetector()
        assert det.run([a, b], graph, llm=None) == []

    def test_silent_for_same_child_topic_edges(self):
        # Both nodes in alg.x — not a sibling cycle (same child).
        a = _node("alg.x.a", kind="definition")
        b = _node("alg.x.b", kind="theorem", uses=["alg.x.a"])
        graph, _ = build_graph([a, b])
        det = TopicCycleDetector()
        assert det.run([a, b], graph, llm=None) == []

    def test_silent_for_cross_root_cycle(self):
        # Cycles between root topics (no common parent) are not in scope here
        # — they're caught at the topic-overview layer, not at sibling-of-X.
        a = _node("topic_alpha.a", kind="definition")
        b = _node("topic_beta.b", kind="theorem", uses=["topic_alpha.a"])
        c = _node("topic_alpha.c", kind="theorem", uses=["topic_beta.b"])
        graph, _ = build_graph([a, b, c])
        det = TopicCycleDetector()
        assert det.run([a, b, c], graph, llm=None) == []

    def test_multi_level_nesting_reports_at_each_parent_level(self):
        # alg.x.y.a ↔ alg.x.z.b creates cycles at both the alg.x level
        # (child topics y vs z) AND the alg level (child topics x.y vs x.z
        # would be the same x rolled up). Only the alg.x level is a true
        # sibling cycle; at alg level, both home topics roll up to the same
        # child (alg.x), which the detector should NOT report.
        a = _node("alg.x.y.a", kind="definition")
        b = _node("alg.x.z.b", kind="definition")
        c = _node("alg.x.z.c", kind="theorem", uses=["alg.x.y.a"])
        d = _node("alg.x.y.d", kind="theorem", uses=["alg.x.z.b"])
        graph, _ = build_graph([a, b, c, d])
        det = TopicCycleDetector()
        diags = det.run([a, b, c, d], graph, llm=None)
        # One diagnostic: the alg.x parent with cycle alg.x.y ↔ alg.x.z.
        # The alg parent would aggregate both to alg.x (same child) and skip.
        assert len(diags) == 1
        msg = diags[0].message
        assert "alg.x" in msg
        assert "alg.x.y" in msg
        assert "alg.x.z" in msg

    def test_proof_plan_edges_excluded(self):
        # Proof-plan uses edges should not be considered part of the
        # topic-cycle aggregation.
        base = _node("alg.x.base", kind="definition")
        target = _node("alg.x.thm", kind="theorem")
        # Plan in sibling topic alg.y referencing alg.x.base
        plan = Node(
            id="alg.y.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="alg.x.thm",
            plan_status="candidate",
            uses=["alg.x.base"],
        )
        graph, diags_graph = build_graph([base, target, plan])
        assert diags_graph == []
        det = TopicCycleDetector()
        # No regular uses edge crosses alg.y ↔ alg.x; only the proof-plan does
        # (and the plan attachment is a separate typed edge). Expect silence.
        assert det.run([base, target, plan], graph, llm=None) == []
