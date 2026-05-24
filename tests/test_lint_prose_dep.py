"""Tests for ProseDepConsistencyDetector (LINT_PROSE_DEP, closes #121 item 5)."""
from __future__ import annotations

from pathlib import Path

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import ProseDepConsistencyDetector
from tools.knowledge.models import Node


def _node(
    node_id: str,
    *,
    kind: str = "definition",
    status: str = "admitted",
    uses: list[str] | None = None,
    body: str = "",
) -> Node:
    return Node(
        id=node_id,
        title=node_id.replace(".", " ").title(),
        kind=kind,
        status=status,
        uses=uses or [],
        body=body,
    )


class TestProseDepConsistencyDetector:
    """Coverage for all 7 specified scenarios."""

    # ------------------------------------------------------------------
    # 1. Definition-kind node body references a known node not in uses
    # ------------------------------------------------------------------
    def test_definition_body_ref_missing_from_uses_emits_warning(self):
        target = _node("alg.group_identity")
        source = _node(
            "alg.uniqueness",
            kind="definition",
            body="This node uses [[node:alg.group_identity]] in its prose.",
            uses=[],
        )
        graph, _ = build_graph([source, target])
        det = ProseDepConsistencyDetector()
        diags = det.run([source, target], graph, llm=None)

        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_PROSE_DEP"
        assert d.node_id == "alg.uniqueness"
        assert d.related == ("alg.group_identity",)
        assert "alg.group_identity" in d.message

    # ------------------------------------------------------------------
    # 2. Theorem-kind node body (outside proof) refs node not in uses
    # ------------------------------------------------------------------
    def test_theorem_body_outside_proof_ref_missing_from_uses_emits_warning(self):
        prereq = _node("alg.subgroup")
        thm = _node(
            "alg.lagrange",
            kind="theorem",
            body=(
                "Let [[node:alg.subgroup]] be a subgroup.\n\n"
                "**Proof.** Omitted."
            ),
            uses=[],
        )
        graph, _ = build_graph([prereq, thm])
        det = ProseDepConsistencyDetector()
        diags = det.run([prereq, thm], graph, llm=None)

        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_PROSE_DEP"
        assert d.node_id == "alg.lagrange"
        assert d.related == ("alg.subgroup",)

    # ------------------------------------------------------------------
    # 3. Same ref twice in body but not in uses → only 1 warning (dedup)
    # ------------------------------------------------------------------
    def test_repeated_ref_not_in_uses_deduplicates_to_one_warning(self):
        target = _node("alg.identity")
        source = _node(
            "alg.prop",
            body=(
                "See [[node:alg.identity]] and also [[node:alg.identity]]."
            ),
            uses=[],
        )
        graph, _ = build_graph([source, target])
        det = ProseDepConsistencyDetector()
        diags = det.run([source, target], graph, llm=None)

        assert len(diags) == 1
        assert diags[0].related == ("alg.identity",)

    # ------------------------------------------------------------------
    # 4. Body ref to a node that IS in uses → 0 warnings
    # ------------------------------------------------------------------
    def test_ref_in_uses_produces_no_warning(self):
        target = _node("alg.base")
        source = _node(
            "alg.derived",
            body="Relies on [[node:alg.base]] by construction.",
            uses=["alg.base"],
        )
        graph, _ = build_graph([source, target])
        det = ProseDepConsistencyDetector()
        diags = det.run([source, target], graph, llm=None)

        assert diags == []

    # ------------------------------------------------------------------
    # 5. Body ref to unknown node-id → 0 warnings (check.py handles it)
    # ------------------------------------------------------------------
    def test_ref_to_unknown_node_produces_no_warning(self):
        source = _node(
            "alg.foo",
            body="See [[node:alg.does_not_exist]] for background.",
            uses=[],
        )
        graph, _ = build_graph([source])
        det = ProseDepConsistencyDetector()
        diags = det.run([source], graph, llm=None)

        assert diags == []

    # ------------------------------------------------------------------
    # 6. Self-reference [[node:n.self]] in body → 0 warnings
    # ------------------------------------------------------------------
    def test_self_reference_in_body_produces_no_warning(self):
        node = _node(
            "alg.self_ref",
            body="This node is [[node:alg.self_ref]] itself.",
            uses=[],
        )
        graph, _ = build_graph([node])
        det = ProseDepConsistencyDetector()
        diags = det.run([node], graph, llm=None)

        assert diags == []

    # ------------------------------------------------------------------
    # 7. Empty body / no refs → 0 warnings
    # ------------------------------------------------------------------
    def test_empty_body_produces_no_warning(self):
        node = _node("alg.empty", body="")
        graph, _ = build_graph([node])
        det = ProseDepConsistencyDetector()
        diags = det.run([node], graph, llm=None)

        assert diags == []

    def test_body_without_refs_produces_no_warning(self):
        node = _node(
            "alg.plain",
            body="This node has plain prose with no node references.",
        )
        graph, _ = build_graph([node])
        det = ProseDepConsistencyDetector()
        diags = det.run([node], graph, llm=None)

        assert diags == []

    # ------------------------------------------------------------------
    # Bonus: needs_llm is False and code is correct
    # ------------------------------------------------------------------
    def test_detector_metadata(self):
        det = ProseDepConsistencyDetector()
        assert det.code == "LINT_PROSE_DEP"
        assert det.needs_llm is False
