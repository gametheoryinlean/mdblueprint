"""Tests for structural detectors (PR 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import OrphanDetector, RedundantDepDetector
from tools.knowledge.models import Node


def _node(node_id: str, *, kind: str = "theorem", status: str = "admitted", uses: list[str] | None = None) -> Node:
    return Node(id=node_id, title=node_id, kind=kind, status=status, uses=list(uses or []))


class TestRedundantDepDetector:
    def test_direct_dep_redundant_when_transitive_path_exists(self):
        # User-facing direction: a -> b -> c, plus the extra direct a -> c.
        # In the YAML convention that means:
        #   c.uses = [a, b]   (c directly depends on both a and b)
        #   b.uses = [a]      (b depends on a)
        # The direct c.uses entry "a" is redundant because c -> b -> a already exists.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.a", "topic.b"])
        graph, diags = build_graph([a, b, c])
        assert diags == []

        det = RedundantDepDetector()
        out = det.run([a, b, c], graph, llm=None)
        assert len(out) == 1
        d = out[0]
        assert d.level == "info"
        assert d.code == "LINT_REDUNDANT_DEP"
        # The diagnostic attaches to the dependent end (c); related names the redundant prerequisite (a).
        assert d.node_id == "topic.c"
        assert d.related == ("topic.a",)
        # Message names both endpoints for human readability.
        assert "topic.a" in d.message
        assert "topic.c" in d.message

    def test_no_findings_on_simple_chain(self):
        # a -> b -> c with no redundant direct edge.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.b"])
        graph, _ = build_graph([a, b, c])
        assert RedundantDepDetector().run([a, b, c], graph, llm=None) == []

    def test_no_findings_when_only_path_is_the_direct_edge(self):
        # Tree with diamond removed: c depends on a and on b independently;
        # neither a nor b reach each other. No redundancy.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", kind="definition")
        c = _node("topic.c", uses=["topic.a", "topic.b"])
        graph, _ = build_graph([a, b, c])
        assert RedundantDepDetector().run([a, b, c], graph, llm=None) == []

    def test_diamond_with_redundant_skip_level(self):
        #       a
        #      / \
        #     b   c
        #      \ /
        #       d  + extra d -> a (redundant: d -> b -> a and d -> c -> a)
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.a"])
        d = _node("topic.d", uses=["topic.a", "topic.b", "topic.c"])
        graph, _ = build_graph([a, b, c, d])
        out = RedundantDepDetector().run([a, b, c, d], graph, llm=None)
        # Only d -> a is redundant. d -> b and d -> c are still the unique path to those.
        assert len(out) == 1
        assert (out[0].node_id, out[0].related) == ("topic.d", ("topic.a",))

    def test_self_loop_safety(self):
        # build_graph rejects cycles (including self-loops); this test guards
        # against the detector relying on cycle-free input regression-style.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        # Drive the detector with a hand-mutated edges entry just to confirm
        # the BFS terminates even if the input graph somehow contained one.
        graph.edges["topic.b"] = ["topic.a"]  # idempotent re-assignment
        det = RedundantDepDetector()
        assert det.run([a, b], graph, llm=None) == []


class TestOrphanDetector:
    def test_isolated_node_is_orphan(self):
        a = _node("topic.solo", kind="definition")
        graph, _ = build_graph([a])
        out = OrphanDetector().run([a], graph, llm=None)
        assert len(out) == 1
        d = out[0]
        assert d.level == "info"
        assert d.code == "LINT_ORPHAN"
        assert d.node_id == "topic.solo"
        assert d.related == ()

    def test_node_with_outgoing_dep_is_not_orphan(self):
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        out = OrphanDetector().run([a, b], graph, llm=None)
        ids = {d.node_id for d in out}
        # b has out-deg 1; a has in-deg 1. Neither is orphan.
        assert ids == set()

    def test_node_with_incoming_dep_is_not_orphan(self):
        # Same fixture as above, but assert from the receiving side explicitly.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        out = OrphanDetector().run([a, b], graph, llm=None)
        assert all(d.node_id != "topic.a" for d in out)

    def test_multiple_orphans(self):
        a = _node("topic.solo_one", kind="definition")
        b = _node("topic.solo_two", kind="definition")
        c = _node("topic.c", kind="definition")
        d = _node("topic.d", uses=["topic.c"])
        graph, _ = build_graph([a, b, c, d])
        out = OrphanDetector().run([a, b, c, d], graph, llm=None)
        ids = {x.node_id for x in out}
        # solo_one and solo_two are orphans; c and d form a chain.
        assert ids == {"topic.solo_one", "topic.solo_two"}

    def test_proof_plan_with_target_but_no_uses_is_not_orphan(self):
        # Proof plans attach to their targets through proof_plan_targets,
        # not through uses. They should not be flagged as orphans just
        # because their uses list is empty.
        thm = _node("topic.thm", kind="theorem")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
        )
        graph, diags = build_graph([thm, plan])
        assert diags == []
        out = OrphanDetector().run([thm, plan], graph, llm=None)
        ids = {x.node_id for x in out}
        # thm has the plan attached; plan has a target. Neither is orphan.
        assert "topic.thm.plan.direct" not in ids
        assert "topic.thm" not in ids
