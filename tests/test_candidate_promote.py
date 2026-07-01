"""`mdblueprint-candidate promote` — issue #159 success criterion #3.

Promoting a verified candidate flips the canonical's promoted pointer and
proof status, retires the previously-promoted sibling to ``abandoned``,
and emits a promotion review report.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tools.knowledge.candidate import promote_candidate, spawn_candidate
from tools.knowledge.parser import parse_file, scan_directory


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body).lstrip(), encoding="utf-8")


@pytest.fixture
def kb_with_two_candidates(tmp_path: Path) -> Path:
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
    # spawn -> migrates (cand_a promoted) + creates cand_b (candidate)
    spawn_candidate("topic.thm", knowledge_root=tmp_path)
    return tmp_path


def _mark_proof_accepted(candidate_path: Path) -> None:
    """Fill in cand_b's proof and mark it accepted, simulating verification."""
    text = candidate_path.read_text(encoding="utf-8")
    text = text.replace("proof: gap", "proof: accepted")
    text = text.replace("*Proof.* TODO", "*Proof.* An alternative argument.")
    candidate_path.write_text(text, encoding="utf-8")


class TestPromote:
    def test_promote_flips_pointer_and_retires_previous(self, kb_with_two_candidates):
        root = kb_with_two_candidates
        cand_b = root / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        _mark_proof_accepted(cand_b)

        result = promote_candidate(cand_b, knowledge_root=root)
        assert result.success, result.diagnostics

        canonical = parse_file(root / "nodes" / "topic" / "thm" / "canonical.md")
        assert canonical.promoted_candidate == "cand_b"
        assert canonical.verification is not None
        assert canonical.verification.proof == "accepted"

        cand_a = parse_file(root / "nodes" / "topic" / "thm" / "candidates" / "cand_a.md")
        cand_b_node = parse_file(cand_b)
        assert cand_b_node.status == "promoted"
        assert cand_a.status == "abandoned"
        assert cand_a.abandoned_reason and "cand_b" in cand_a.abandoned_reason

    def test_promote_emits_review_report(self, kb_with_two_candidates):
        root = kb_with_two_candidates
        cand_b = root / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        _mark_proof_accepted(cand_b)
        result = promote_candidate(cand_b, knowledge_root=root)
        assert result.review_path is not None
        assert result.review_path.exists()
        reviews_dir = root / "reviews"
        reports = list(reviews_dir.rglob("promotion-*.md"))
        assert len(reports) == 1
        text = reports[0].read_text(encoding="utf-8")
        assert "cand_b" in text

    def test_promote_rejects_unaccepted_proof(self, kb_with_two_candidates):
        root = kb_with_two_candidates
        cand_b = root / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        # cand_b still has proof: gap / placeholder.
        result = promote_candidate(cand_b, knowledge_root=root)
        assert not result.success
        assert any("accepted" in d.message.lower() for d in result.diagnostics)
        # State untouched: cand_a still promoted.
        canonical = parse_file(root / "nodes" / "topic" / "thm" / "canonical.md")
        assert canonical.promoted_candidate == "cand_a"
