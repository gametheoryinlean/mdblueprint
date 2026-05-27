"""Parser-level tests for the multi-candidate dir layout (PR 1).

These verify that scan_directory picks up canonical.md + candidates/*.md
without any change to the rglob walk, and that the six new frontmatter
fields are populated on Node.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tools.knowledge.parser import parse_file, scan_directory


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body).lstrip(), encoding="utf-8")


@pytest.fixture
def dir_layout_root(tmp_path: Path) -> Path:
    """Build a minimal multi-candidate tree under tmp_path."""
    canonical_dir = tmp_path / "nodes" / "ext_games" / "spe"
    _write(canonical_dir / "canonical.md", """
        ---
        id: ext_games.spe
        title: Subgame Perfect Equilibrium
        kind: theorem
        status: admitted
        candidate_layout: multi
        promoted_candidate: cand_a
        candidates:
          - cand_a
          - cand_b
        uses:
          - ext_games.subgame
        verification:
          statement: accepted
          proof: accepted
        lean:
          modules: [Lib.SPE]
          declarations: [Lib.IsSPE]
        ---

        # Subgame Perfect Equilibrium

        Statement body.
        """)

    _write(canonical_dir / "candidates" / "cand_a.md", """
        ---
        id: ext_games.spe._cand_a
        title: SPE (cand_a)
        kind: theorem
        status: promoted
        candidate_of: ext_games.spe
        candidate_slug: cand_a
        uses:
          - ext_games.subgame
        verification:
          statement: accepted
          proof: accepted
        ---

        # SPE (cand_a)

        Statement body.

        *Proof.* By backward induction.
        """)

    _write(canonical_dir / "candidates" / "cand_b.md", """
        ---
        id: ext_games.spe._cand_b
        title: SPE (cand_b)
        kind: theorem
        status: abandoned
        candidate_of: ext_games.spe
        candidate_slug: cand_b
        abandoned_reason: "verifier rejected on step 3"
        uses:
          - ext_games.subgame
        verification:
          statement: accepted
          proof: critical
        ---

        # SPE (cand_b)

        Statement body.

        *Proof.* Direct construction (fails).
        """)
    return tmp_path


class TestRglobDiscovery:
    def test_scan_finds_canonical_and_candidates(self, dir_layout_root: Path):
        nodes = scan_directory(dir_layout_root / "nodes")
        ids = {n.id for n in nodes}
        assert ids == {"ext_games.spe", "ext_games.spe._cand_a", "ext_games.spe._cand_b"}


class TestFrontmatterFields:
    def test_canonical_fields(self, dir_layout_root: Path):
        node = parse_file(
            dir_layout_root / "nodes" / "ext_games" / "spe" / "canonical.md"
        )
        assert node.id == "ext_games.spe"
        assert node.candidate_layout == "multi"
        assert node.promoted_candidate == "cand_a"
        assert node.candidates == ["cand_a", "cand_b"]
        # Candidates-only fields are unset on canonical
        assert node.candidate_of is None
        assert node.candidate_slug is None
        assert node.abandoned_reason is None

    def test_promoted_candidate_fields(self, dir_layout_root: Path):
        node = parse_file(
            dir_layout_root / "nodes" / "ext_games" / "spe" / "candidates" / "cand_a.md"
        )
        assert node.id == "ext_games.spe._cand_a"
        assert node.candidate_of == "ext_games.spe"
        assert node.candidate_slug == "cand_a"
        assert node.status == "promoted"
        # Canonical-only fields are unset
        assert node.candidate_layout is None
        assert node.promoted_candidate is None
        assert node.candidates == []
        assert node.abandoned_reason is None

    def test_abandoned_candidate_fields(self, dir_layout_root: Path):
        node = parse_file(
            dir_layout_root / "nodes" / "ext_games" / "spe" / "candidates" / "cand_b.md"
        )
        assert node.status == "abandoned"
        assert node.abandoned_reason == "verifier rejected on step 3"


class TestSingleFileCanonicalUnchanged:
    def test_single_file_node_has_no_candidate_fields_set(self, tmp_path: Path):
        _write(tmp_path / "nodes" / "topic" / "x.md", """
            ---
            id: topic.x
            title: X
            kind: theorem
            status: admitted
            uses: []
            verification:
              statement: accepted
              proof: accepted
            lean:
              modules: [Lib.X]
              declarations: [Lib.x]
            ---

            # X

            Body.

            *Proof.* Direct.
            """)
        node = parse_file(tmp_path / "nodes" / "topic" / "x.md")
        assert node.candidate_layout is None
        assert node.candidate_of is None
        assert node.candidate_slug is None
        assert node.promoted_candidate is None
        assert node.candidates == []
        assert node.abandoned_reason is None
