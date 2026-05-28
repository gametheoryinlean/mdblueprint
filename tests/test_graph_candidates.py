"""Graph DAG integration for multi-candidate proofs (issue #159, PR 2).

Only a ``promoted`` candidate contributes proof-graph edges. Its edges
are keyed by the candidate's own id (not the canonical's) — the
publisher in PR 4 resolves canonical → promoted-candidate when rendering.
``candidate`` and ``abandoned`` siblings stay in ``g.nodes`` but
contribute no edges in either direction.
"""
from __future__ import annotations

from tools.knowledge.graph import build_graph
from tools.knowledge.models import Node


def _canonical() -> Node:
    return Node(
        id="topic.thm",
        title="Thm",
        kind="theorem",
        status="admitted",
        candidate_layout="multi",
        promoted_candidate="cand_a",
        candidates=["cand_a", "cand_b"],
        uses=[],
        body="Statement.",
    )


def _helper(local: str) -> Node:
    return Node(
        id=f"topic.{local}",
        title=local,
        kind="lemma",
        status="admitted",
        uses=[],
        body="Helper.",
    )


def _candidate(slug: str, status: str, uses: list[str]) -> Node:
    return Node(
        id=f"topic.thm._{slug}",
        title=f"Thm ({slug})",
        kind="theorem",
        status=status,
        candidate_of="topic.thm",
        candidate_slug=slug,
        uses=uses,
        body="Statement.\n\n*Proof.* x",
    )


class TestPromotedEdges:
    def test_promoted_candidate_uses_become_edges_keyed_by_candidate_id(self):
        helper = _helper("lemma_x")
        canonical = _canonical()
        promoted = _candidate("cand_a", "promoted", ["topic.lemma_x"])
        g, diags = build_graph([helper, canonical, promoted])
        assert [d for d in diags if d.level == "error"] == []
        # Edge keyed by the candidate's own id.
        assert "topic.lemma_x" in g.edges["topic.thm._cand_a"]
        # Reverse edge present.
        assert "topic.thm._cand_a" in g.reverse_edges["topic.lemma_x"]
        # NOT keyed by the canonical id.
        assert "topic.lemma_x" not in g.edges.get("topic.thm", [])


class TestNonPromotedNoEdges:
    def test_abandoned_candidate_contributes_no_edges(self):
        helper = _helper("lemma_y")
        canonical = _canonical()
        abandoned = _candidate("cand_b", "abandoned", ["topic.lemma_y"])
        g, diags = build_graph([helper, canonical, abandoned])
        assert g.edges.get("topic.thm._cand_b", []) == []
        assert "topic.thm._cand_b" not in g.reverse_edges.get("topic.lemma_y", [])
        # But the node is still loaded.
        assert "topic.thm._cand_b" in g.nodes

    def test_unverified_candidate_contributes_no_edges(self):
        helper = _helper("lemma_z")
        canonical = _canonical()
        candidate = _candidate("cand_c", "candidate", ["topic.lemma_z"])
        g, diags = build_graph([helper, canonical, candidate])
        assert g.edges.get("topic.thm._cand_c", []) == []
        assert "topic.thm._cand_c" in g.nodes

    def test_unverified_candidate_missing_dep_does_not_error(self):
        # A work-in-progress candidate may reference helpers that do not
        # exist yet; this must not hard-error the graph build.
        canonical = _canonical()
        candidate = _candidate("cand_c", "candidate", ["topic.does_not_exist"])
        g, diags = build_graph([canonical, candidate])
        errors = [d for d in diags if d.level == "error"]
        assert errors == [], errors
