"""Tests for the fuzzy title / staged-overlap detectors (PR 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import (
    FuzzyTitleDupDetector,
    _normalize,
    _ratio,
)
from tools.knowledge.models import Node


def _node(node_id: str, title: str, *, kind: str = "theorem", status: str = "admitted", body: str = "") -> Node:
    return Node(id=node_id, title=title, kind=kind, status=status, body=body)


class TestNormalize:
    def test_lowercases_and_collapses_whitespace(self):
        assert _normalize("Group  Identity   Is\tUnique") == "group identity is unique"

    def test_strips_leading_and_trailing_punctuation(self):
        assert _normalize("  *Group Identity Is Unique.*  ") == "group identity is unique"

    def test_preserves_internal_punctuation(self):
        # Internal punctuation stays so a sentence-level difference is still distinguishable.
        assert _normalize("If g, h in G, then gh = hg") == "if g, h in g, then gh = hg"


class TestRatio:
    def test_identical_strings_return_one(self):
        assert _ratio("group identity is unique", "group identity is unique") == 1.0

    def test_unrelated_strings_return_low_score(self):
        assert _ratio("group identity is unique", "cauchy schwarz inequality") < 0.5

    def test_near_duplicates_clear_default_threshold(self):
        a = "group identity is unique"
        b = "group identity is unique."
        assert _ratio(_normalize(a), _normalize(b)) >= 0.92


class TestFuzzyTitleDupDetector:
    def test_emits_warning_for_punctuation_variant(self):
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        diags = det.run([a, b], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_FUZZY_DUP"
        # `related` carries the other node's id; the source node_id is the
        # lexicographically smaller of the pair so the diagnostic is stable.
        assert d.node_id == "alg.x"
        assert d.related == ("alg.y",)

    def test_does_not_emit_for_unrelated_titles(self):
        a = _node("alg.group", "Group Identity Is Unique")
        b = _node("ana.cauchy", "Cauchy Schwarz Inequality")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        assert det.run([a, b], graph, llm=None) == []

    def test_ignores_staged_nodes(self):
        # FuzzyTitleDup only considers admitted nodes — staged-vs-admitted
        # overlap is the StagedAdmittedOverlapDetector's job.
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.", status="staged")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        assert det.run([a, b], graph, llm=None) == []

    def test_threshold_is_respected(self):
        # 0.86 ratio pair should NOT trigger at 0.92 but SHOULD at 0.80.
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity in a group is unique element")
        graph, _ = build_graph([a, b])
        assert FuzzyTitleDupDetector(threshold=0.92).run([a, b], graph, llm=None) == []
        loose = FuzzyTitleDupDetector(threshold=0.50).run([a, b], graph, llm=None)
        assert len(loose) == 1

    def test_uses_statement_when_titles_differ(self):
        # If titles differ but statements are near-identical, still flag.
        a = _node(
            "alg.alpha",
            "Lemma One",
            body="## Statement\nFor every group, the identity element is unique.\n",
        )
        b = _node(
            "alg.beta",
            "Lemma Two",
            body="## Statement\nFor every group, the identity element is unique.\n",
        )
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        diags = det.run([a, b], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].code == "LINT_FUZZY_DUP"

    def test_pair_is_reported_only_once(self):
        # The all-pairs scan must emit a single diagnostic per unordered pair.
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.")
        graph, _ = build_graph([a, b])
        diags = FuzzyTitleDupDetector(threshold=0.92).run([a, b], graph, llm=None)
        ids_seen = [(d.node_id, d.related) for d in diags]
        assert len(ids_seen) == 1
        assert ids_seen[0] == ("alg.x", ("alg.y",))
