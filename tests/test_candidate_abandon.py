"""`mdblueprint-candidate abandon` — issue #159 success criterion #6.

Abandoning a candidate flips its status + reason and emits a review, but
must NOT delete independently-admitted helper nodes the candidate
introduced, and must refuse to abandon the currently-promoted candidate.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tools.knowledge.candidate import abandon_candidate, list_candidates, spawn_candidate
from tools.knowledge.parser import parse_file


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body).lstrip(), encoding="utf-8")


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    nodes = tmp_path / "nodes" / "topic"
    _write(nodes / "helper_a.md", """
        ---
        id: topic.helper_a
        title: Helper A
        kind: lemma
        status: admitted
        uses: []
        verification: {statement: accepted, proof: accepted}
        lean: {modules: [Lib.A], declarations: [Lib.a]}
        ---

        # Helper A

        Helper A holds.

        *Proof.* Trivial.
        """)
    _write(nodes / "thm.md", """
        ---
        id: topic.thm
        title: My Theorem
        kind: theorem
        status: admitted
        uses: [topic.helper_a]
        verification: {statement: accepted, proof: accepted, alignment: aligned}
        lean: {modules: [Lib.Thm], declarations: [Lib.thm]}
        ---

        # My Theorem

        The theorem statement holds for all inputs.

        *Proof.* From Helper A.
        """)
    spawn_candidate("topic.thm", knowledge_root=tmp_path)  # cand_a promoted, cand_b candidate
    return tmp_path


class TestAbandon:
    def test_abandon_non_promoted_candidate(self, kb: Path):
        cand_b = kb / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        result = abandon_candidate(cand_b, knowledge_root=kb, reason="dead end")
        assert result.success, result.diagnostics
        node = parse_file(cand_b)
        assert node.status == "abandoned"
        assert node.abandoned_reason == "dead end"
        # Canonical pointer untouched.
        canonical = parse_file(kb / "nodes" / "topic" / "thm" / "canonical.md")
        assert canonical.promoted_candidate == "cand_a"

    def test_abandon_emits_review(self, kb: Path):
        cand_b = kb / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        result = abandon_candidate(cand_b, knowledge_root=kb, reason="dead end")
        assert result.review_path is not None and result.review_path.exists()
        reports = list((kb / "reviews").rglob("abandon-*.md"))
        assert len(reports) == 1

    def test_abandon_promoted_candidate_is_rejected(self, kb: Path):
        cand_a = kb / "nodes" / "topic" / "thm" / "candidates" / "cand_a.md"
        result = abandon_candidate(cand_a, knowledge_root=kb, reason="nope")
        assert not result.success
        assert any("promoted" in d.message.lower() for d in result.diagnostics)
        # Untouched.
        assert parse_file(cand_a).status == "promoted"

    def test_abandon_preserves_independently_admitted_helper(self, kb: Path):
        """Success criterion #6: abandoning a candidate that introduced a
        helper does not delete the helper."""
        nodes = kb / "nodes" / "topic"
        # A helper introduced by cand_b's proof strategy, admitted on its own.
        _write(nodes / "cand_b_helper.md", """
            ---
            id: topic.cand_b_helper
            title: Cand B Helper
            kind: lemma
            status: admitted
            uses: []
            verification: {statement: accepted, proof: accepted}
            lean: {modules: [Lib.CBH], declarations: [Lib.cbh]}
            ---

            # Cand B Helper

            A helper lemma.

            *Proof.* Trivial.
            """)
        cand_b = nodes / "thm" / "candidates" / "cand_b.md"
        # Point cand_b at the helper (format-agnostic: the dependency id
        # appears only in cand_b's `uses`).
        text = cand_b.read_text(encoding="utf-8")
        text = text.replace("topic.helper_a", "topic.cand_b_helper")
        cand_b.write_text(text, encoding="utf-8")

        helper_path = nodes / "cand_b_helper.md"
        before = helper_path.read_text(encoding="utf-8")
        result = abandon_candidate(cand_b, knowledge_root=kb, reason="strategy abandoned")
        assert result.success, result.diagnostics
        assert helper_path.exists()
        assert helper_path.read_text(encoding="utf-8") == before
        assert parse_file(helper_path).status == "admitted"


class TestList:
    def test_list_reports_slug_status(self, kb: Path):
        infos = list_candidates("topic.thm", knowledge_root=kb)
        by_slug = {i.slug: i for i in infos}
        assert by_slug["cand_a"].status == "promoted"
        assert by_slug["cand_a"].is_promoted is True
        assert by_slug["cand_b"].status == "candidate"
        assert by_slug["cand_b"].is_promoted is False
