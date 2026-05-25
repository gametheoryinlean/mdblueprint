"""Tests for LINT_TOPIC_LEAN_ALIGNMENT and LINT_LEAN_MODULE_FRAGMENTED detectors."""
from __future__ import annotations

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import LeanModuleFragmentedDetector, TopicLeanAlignmentDetector
from tools.knowledge.models import LeanRef, Node


# ── helpers ───────────────────────────────────────────────────────────────────


def _node(
    node_id: str,
    *,
    kind: str = "theorem",
    status: str = "admitted",
    lean_modules: list[str] | None = None,
    primary_topic: str | None = None,
    topic_lean_alignment: str | None = None,
) -> Node:
    lean = (
        LeanRef(modules=list(lean_modules), declarations=[])
        if lean_modules is not None
        else None
    )
    return Node(
        id=node_id,
        title=node_id,
        kind=kind,
        status=status,
        lean=lean,
        primary_topic=primary_topic,
        topic_lean_alignment=topic_lean_alignment,
    )


# ── LINT_TOPIC_LEAN_ALIGNMENT ─────────────────────────────────────────────────


class TestTopicLeanAlignmentDetector:
    """Tests for LINT_TOPIC_LEAN_ALIGNMENT detector."""

    def test_aligned_node_is_silent(self):
        """Node with blueprint root 'core' and Lean module 'EconCSLib.Core.Preference'
        should produce no finding.
        """
        node = _node(
            "core.preference.def",
            lean_modules=["EconCSLib.Core.Preference"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        assert det.run([node], graph, llm=None) == []

    def test_misaligned_node_produces_warning(self):
        """Node with blueprint root 'core' but Lean module root 'linear_algebra'
        should produce 1 warning.
        """
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_TOPIC_LEAN_ALIGNMENT"
        assert d.node_id == "core.linear_algebra.farkas_lemma"

    def test_misaligned_diagnostic_contains_lean_module_in_related(self):
        """Diagnostic should carry the misaligned Lean module name in related."""
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        assert "EconCSLib.LinearAlgebra.Farkas" in diags[0].related

    def test_misaligned_diagnostic_message_is_single_line_and_informative(self):
        """Message should be a single line mentioning both roots."""
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        diags = det.run([node], graph, llm=None)
        msg = diags[0].message
        # single line
        assert "\n" not in msg
        # mentions blueprint root and lean root
        assert "core" in msg
        assert "linear_algebra" in msg

    def test_multi_module_one_matches_is_silent(self):
        """If at least one Lean module's root matches, no finding is emitted."""
        node = _node(
            "core.preference.def",
            lean_modules=[
                "EconCSLib.LinearAlgebra.Farkas",  # misaligned
                "EconCSLib.Core.Preference",        # aligned
            ],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        assert det.run([node], graph, llm=None) == []

    def test_divergent_opt_out_suppresses_finding(self):
        """Node with topic_lean_alignment: divergent should be skipped entirely."""
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
            topic_lean_alignment="divergent",
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        assert det.run([node], graph, llm=None) == []

    def test_alias_normalization_is_silent(self):
        """A Lean singular-convention root that is aliased to the blueprint plural
        convention should be treated as equivalent via the alias table.

        We inject a custom alias ('concept_item' -> 'concept_items') to keep
        the test domain-agnostic while exercising the same code path.
        """
        import tools.knowledge.lint._detectors as _det_mod
        original = dict(_det_mod._BLUEPRINT_LEAN_ROOT_ALIASES)
        try:
            _det_mod._BLUEPRINT_LEAN_ROOT_ALIASES["concept_item"] = "concept_items"
            node = _node(
                "concept_items.core.best_response",
                lean_modules=["SomeLib.ConceptItem.Core"],
            )
            graph, _ = build_graph([node])
            det = TopicLeanAlignmentDetector()
            assert det.run([node], graph, llm=None) == []
        finally:
            _det_mod._BLUEPRINT_LEAN_ROOT_ALIASES.clear()
            _det_mod._BLUEPRINT_LEAN_ROOT_ALIASES.update(original)

    def test_node_with_no_lean_modules_is_silent(self):
        """Node without any lean modules should produce no finding."""
        node = _node("core.linear_algebra.farkas_lemma")
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        assert det.run([node], graph, llm=None) == []

    def test_aligned_opt_out_does_not_suppress(self):
        """topic_lean_alignment: aligned should not suppress a genuine mismatch
        (only 'divergent' is a skip signal).
        """
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
            topic_lean_alignment="aligned",
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        # "aligned" means author *claims* alignment, so we still flag misalignment
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1

    def test_primary_topic_used_for_root_derivation(self):
        """primary_topic overrides the id-derived topic for root computation."""
        node = _node(
            "core.preference.def",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
            primary_topic="linear_algebra.preference",
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        # blueprint root becomes 'linear_algebra' via primary_topic
        assert det.run([node], graph, llm=None) == []


# ── LINT_LEAN_MODULE_FRAGMENTED ───────────────────────────────────────────────


class TestLeanModuleFragmentedDetector:
    """Tests for LINT_LEAN_MODULE_FRAGMENTED detector."""

    def test_single_node_for_lean_root_is_silent(self):
        """Lean root with only 1 node should produce no finding."""
        node = _node(
            "core.linear_algebra.farkas_lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
        )
        graph, _ = build_graph([node])
        det = LeanModuleFragmentedDetector()
        assert det.run([node], graph, llm=None) == []

    def test_same_blueprint_root_is_silent(self):
        """5 nodes all in same blueprint root should produce no finding."""
        nodes = [
            _node(
                f"linear_algebra.module{i}.lemma",
                lean_modules=["EconCSLib.LinearAlgebra.Module"],
            )
            for i in range(5)
        ]
        graph, _ = build_graph(nodes)
        det = LeanModuleFragmentedDetector()
        assert det.run(nodes, graph, llm=None) == []

    def test_fragmented_lean_root_produces_info(self):
        """6 nodes spread across 2 blueprint roots (5 + 1) should emit 1 info."""
        nodes_group_a = [
            _node(
                f"core.linear_algebra.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.Core"],
            )
            for i in range(5)
        ]
        node_b = _node(
            "zero_sum.applications.perron_frobenius",
            lean_modules=["EconCSLib.LinearAlgebra.PerronFrobenius"],
        )
        all_nodes = nodes_group_a + [node_b]
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        diags = det.run(all_nodes, graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"
        assert d.code == "LINT_LEAN_MODULE_FRAGMENTED"

    def test_fragmented_diagnostic_names_both_roots(self):
        """Message should mention both blueprint roots and their node counts."""
        nodes_group_a = [
            _node(
                f"core.linear_algebra.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.Core"],
            )
            for i in range(5)
        ]
        node_b = _node(
            "zero_sum.applications.perron_frobenius",
            lean_modules=["EconCSLib.LinearAlgebra.PerronFrobenius"],
        )
        all_nodes = nodes_group_a + [node_b]
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        diags = det.run(all_nodes, graph, llm=None)
        msg = diags[0].message
        assert "core" in msg
        assert "zero_sum" in msg
        # counts
        assert "5" in msg
        assert "1" in msg

    def test_fragmented_aggregate_is_info_not_warning(self):
        """Severity must be info, not warning."""
        nodes_group_a = [
            _node(
                f"core.linear_algebra.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.Core"],
            )
            for i in range(3)
        ]
        node_b = _node(
            "zero_sum.applications.perron_frobenius",
            lean_modules=["EconCSLib.LinearAlgebra.PerronFrobenius"],
        )
        all_nodes = nodes_group_a + [node_b]
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        diags = det.run(all_nodes, graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "info"

    def test_fragmented_one_per_lean_root_not_per_node(self):
        """Aggregate detector emits exactly 1 diagnostic per Lean module root."""
        nodes_a = [
            _node(f"core.x.lemma{i}", lean_modules=["EconCSLib.LinearAlgebra.X"])
            for i in range(3)
        ]
        nodes_b = [
            _node(f"strategy.x.lemma{i}", lean_modules=["EconCSLib.LinearAlgebra.X"])
            for i in range(3)
        ]
        all_nodes = nodes_a + nodes_b
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        diags = det.run(all_nodes, graph, llm=None)
        # exactly 1 diagnostic for the single fragmented lean root 'linear_algebra'
        assert len(diags) == 1

    def test_all_divergent_opt_out_suppresses_fragmented(self):
        """If all nodes with a given Lean root have topic_lean_alignment: divergent,
        the aggregate finding should be suppressed.
        """
        nodes_a = [
            _node(
                f"core.x.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.X"],
                topic_lean_alignment="divergent",
            )
            for i in range(3)
        ]
        nodes_b = [
            _node(
                f"strategy.x.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.X"],
                topic_lean_alignment="divergent",
            )
            for i in range(3)
        ]
        all_nodes = nodes_a + nodes_b
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        assert det.run(all_nodes, graph, llm=None) == []

    def test_partial_divergent_still_emits(self):
        """If only *some* nodes are divergent, the finding is still emitted
        (suppression requires ALL nodes to be divergent).
        """
        nodes_a = [
            _node(
                f"core.x.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.X"],
                topic_lean_alignment="divergent",
            )
            for i in range(3)
        ]
        nodes_b = [
            _node(
                f"strategy.x.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.X"],
            )
            for i in range(3)
        ]
        all_nodes = nodes_a + nodes_b
        graph, _ = build_graph(all_nodes)
        det = LeanModuleFragmentedDetector()
        diags = det.run(all_nodes, graph, llm=None)
        assert len(diags) == 1


# ── Built-in singular/plural alias tests ─────────────────────────────────────


class TestBuiltinSingularPluralAliases:
    """Tests that the 7 built-in game-theory plural↔singular aliases work."""

    @pytest.mark.parametrize("singular,plural", [
        ("strategic_game", "strategic_games"),
        ("extensive_game", "extensive_games"),
        ("repeated_game", "repeated_games"),
        ("stochastic_game", "stochastic_games"),
        ("coalitional_game", "coalitional_games"),
        ("bayesian_game", "bayesian_games"),
        ("differential_game", "differential_games"),
    ])
    def test_default_alias_maps_singular_lean_to_plural_blueprint(
        self, singular: str, plural: str
    ) -> None:
        """Blueprint root '<plural>', Lean module 'SomeLib.<Singular>.X' → no finding."""
        # Convert snake_case singular to PascalCase for the module name
        pascal = "".join(w.title() for w in singular.split("_"))
        node = _node(
            f"{plural}.core.some_theorem",
            lean_modules=[f"SomeLib.{pascal}.Core"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector()
        assert det.run([node], graph, llm=None) == [], (
            f"Expected no finding for blueprint root {plural!r} with "
            f"Lean module root {singular!r} (built-in alias should handle it)"
        )


# ── extra_aliases: merge and override tests ───────────────────────────────────


class TestExtraAliases:
    """Tests for project-level extra_aliases on both detectors."""

    def test_extra_alias_merges_with_default(self) -> None:
        """Pass extra_aliases={'linear_algebra': 'linear_programming'};
        node blueprint root 'linear_programming', Lean 'EconCSLib.LinearAlgebra.X'
        → no finding.
        """
        node = _node(
            "linear_programming.farkas.lemma",
            lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
        )
        graph, _ = build_graph([node])
        det = TopicLeanAlignmentDetector(
            extra_aliases={"linear_algebra": "linear_programming"}
        )
        assert det.run([node], graph, llm=None) == []

    def test_extra_alias_overrides_default(self) -> None:
        """extra_aliases={'strategic_game': 'games'} overrides the built-in
        'strategic_game' → 'strategic_games' mapping.

        - blueprint root 'games', Lean 'EconCSLib.StrategicGame.X' → no finding
          (alias remaps to 'games').
        - blueprint root 'strategic_games', Lean 'EconCSLib.StrategicGame.X' → fires
          (alias now maps to 'games', not 'strategic_games').
        """
        extra = {"strategic_game": "games"}

        # With override: 'games' blueprint root aligns
        node_ok = _node(
            "games.core.nash_equilibrium",
            lean_modules=["EconCSLib.StrategicGame.Core"],
        )
        graph_ok, _ = build_graph([node_ok])
        det = TopicLeanAlignmentDetector(extra_aliases=extra)
        assert det.run([node_ok], graph_ok, llm=None) == []

        # With override: 'strategic_games' blueprint root no longer aligns
        node_fail = _node(
            "strategic_games.core.nash_equilibrium",
            lean_modules=["EconCSLib.StrategicGame.Core"],
        )
        graph_fail, _ = build_graph([node_fail])
        diags = det.run([node_fail], graph_fail, llm=None)
        assert len(diags) == 1
        assert diags[0].code == "LINT_TOPIC_LEAN_ALIGNMENT"

    def test_lean_module_fragmented_respects_extra_aliases(self) -> None:
        """When extra_aliases maps a Lean root to a single blueprint root,
        nodes that previously appeared to span two blueprint roots are now
        consolidated and the fragmented finding is suppressed.

        Without extra alias: nodes in 'linear_programming' and 'linear_algebra'
        blueprint roots would both normalise their Lean root to 'linear_algebra'
        → fragmented finding.

        With extra_aliases={'linear_algebra': 'linear_programming'}: both
        blueprint roots now canonicalise to 'linear_programming' before
        comparison, so they're seen as the same root → no fragmented finding.
        """
        nodes_a = [
            _node(
                f"linear_programming.farkas.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.Farkas"],
            )
            for i in range(3)
        ]
        nodes_b = [
            _node(
                f"linear_algebra.core.lemma{i}",
                lean_modules=["EconCSLib.LinearAlgebra.Core"],
            )
            for i in range(3)
        ]
        all_nodes = nodes_a + nodes_b
        graph, _ = build_graph(all_nodes)

        # Without alias: fragmented (two distinct blueprint roots)
        det_no_alias = LeanModuleFragmentedDetector()
        diags_no_alias = det_no_alias.run(all_nodes, graph, llm=None)
        assert len(diags_no_alias) >= 1, (
            "Expected fragmented finding without alias"
        )

        # With alias: both roots canonicalise to 'linear_programming' → silent
        det_with_alias = LeanModuleFragmentedDetector(
            extra_aliases={"linear_algebra": "linear_programming"}
        )
        diags_with_alias = det_with_alias.run(all_nodes, graph, llm=None)
        assert diags_with_alias == []
