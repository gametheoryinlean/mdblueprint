"""Regression: lint's fuzzy-dup detector must not flag a canonical and its
promoted candidate as a duplicate pair.

Issue #159 design decision #4 keeps ``promoted`` outside
``ADMITTED_STATUSES``, so the existing detector naturally skips promoted
candidates. This test pins that behaviour: if a future change adds
``promoted`` to the detector's pool without a sibling-suppression guard,
this test breaks.
"""
from __future__ import annotations

from pathlib import Path

from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.lint._detectors import FuzzyTitleDupDetector
from tools.knowledge.models import Node


def _canonical(*, file_path: Path | None = None) -> Node:
    return Node(
        id="topic.thm",
        title="Subgame Perfect Equilibrium",
        kind="theorem",
        status="admitted",
        candidate_layout="multi",
        promoted_candidate="cand_a",
        candidates=["cand_a"],
        body="A strategy profile is a subgame perfect equilibrium if it is a Nash equilibrium in every subgame.",
        file_path=file_path,
    )


def _candidate(*, status: str, file_path: Path | None = None) -> Node:
    return Node(
        id="topic.thm._cand_a",
        title="Subgame Perfect Equilibrium",
        kind="theorem",
        status=status,
        candidate_of="topic.thm",
        candidate_slug="cand_a",
        body="A strategy profile is a subgame perfect equilibrium if it is a Nash equilibrium in every subgame.",
        file_path=file_path,
    )


def test_fuzzy_dup_does_not_flag_canonical_and_promoted_sibling(tmp_path: Path):
    canonical = _canonical(file_path=tmp_path / "canonical.md")
    promoted = _candidate(status="promoted", file_path=tmp_path / "cand_a.md")
    graph, _ = build_graph([canonical, promoted])
    diags = FuzzyTitleDupDetector().run([canonical, promoted], graph, llm=None)
    assert diags == [], f"unexpected lint findings: {diags}"


def test_fuzzy_dup_does_not_flag_canonical_and_candidate_sibling(tmp_path: Path):
    canonical = _canonical(file_path=tmp_path / "canonical.md")
    candidate = _candidate(status="candidate", file_path=tmp_path / "cand_a.md")
    graph, _ = build_graph([canonical, candidate])
    diags = FuzzyTitleDupDetector().run([canonical, candidate], graph, llm=None)
    assert diags == [], f"unexpected lint findings: {diags}"
