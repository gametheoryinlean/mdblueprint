"""Tests for structural detectors (PR 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import RedundantDepDetector
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
