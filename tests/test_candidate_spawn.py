"""`mdblueprint-candidate spawn` — migration + new-attempt creation (PR 3).

Covers issue #159 success criterion #2 (relaxed per the 2026-05-28 plan
mutation): after migrating a single-file canonical to the dir layout the
tree validates, the graph builds, and the dependency set reachable from
the canonical *through its promoted candidate* equals the pre-migration
``uses`` set. Byte-identical graph.json is explicitly NOT required —
migration moves the proof's edges from the canonical node onto the
promoted-candidate node.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tools.knowledge.candidate import spawn_candidate
from tools.knowledge.candidate_layout import (
    canonical_proof_source,
    discover_canonical_groups,
    proof_block_start,
    validate_canonical_groups,
)
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import parse_file, scan_directory


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body).lstrip(), encoding="utf-8")


@pytest.fixture
def single_file_kb(tmp_path: Path) -> Path:
    """A knowledge root with one single-file canonical + two helpers."""
    nodes = tmp_path / "nodes" / "topic"
    _write(nodes / "helper_a.md", """
        ---
        id: topic.helper_a
        title: Helper A
        kind: lemma
        status: admitted
        uses: []
        verification:
          statement: accepted
          proof: accepted
        lean:
          modules: [Lib.A]
          declarations: [Lib.a]
        ---

        # Helper A

        Helper A holds.

        *Proof.* Trivial.
        """)
    _write(nodes / "helper_b.md", """
        ---
        id: topic.helper_b
        title: Helper B
        kind: lemma
        status: admitted
        uses: []
        verification:
          statement: accepted
          proof: accepted
        lean:
          modules: [Lib.B]
          declarations: [Lib.b]
        ---

        # Helper B

        Helper B holds.

        *Proof.* Trivial.
        """)
    _write(nodes / "thm.md", """
        ---
        id: topic.thm
        title: My Theorem
        kind: theorem
        status: admitted
        uses:
          - topic.helper_a
          - topic.helper_b
        verification:
          statement: accepted
          proof: accepted
          alignment: aligned
        lean:
          modules: [Lib.Thm]
          declarations: [Lib.thm]
        ---

        # My Theorem

        The theorem statement holds for all inputs.

        *Proof.* Combine Helper A and Helper B.
        """)
    return tmp_path


def _reachable_deps(canonical_id: str, root: Path) -> set[str]:
    nodes = scan_directory(root / "nodes")
    by_id = {n.id: n for n in nodes}
    groups = {g.canonical.id: g for g in discover_canonical_groups(nodes)}
    g, _ = build_graph(nodes)
    source = canonical_proof_source(canonical_id, by_id, groups)
    assert source is not None
    # one-hop deps of the proof source (helpers are leaves here)
    return set(g.edges.get(source.id, []))


class TestMigration:
    def test_spawn_migrates_single_file_to_dir_layout(self, single_file_kb: Path):
        result = spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        assert result.success, result.diagnostics
        assert result.migrated is True

        topic = single_file_kb / "nodes" / "topic"
        assert not (topic / "thm.md").exists()
        assert (topic / "thm" / "canonical.md").exists()
        assert (topic / "thm" / "candidates" / "cand_a.md").exists()
        # The new attempt is cand_b (cand_a is the migrated original).
        assert result.new_slug == "cand_b"
        assert (topic / "thm" / "candidates" / "cand_b.md").exists()

    def test_migrated_tree_validates_and_builds(self, single_file_kb: Path):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        nodes = scan_directory(single_file_kb / "nodes")
        by_id = {n.id: n for n in nodes}
        groups = discover_canonical_groups(nodes)
        v = [d for d in validate_canonical_groups(groups, by_id) if d.level == "error"]
        assert v == [], v
        _, gdiags = build_graph(nodes)
        assert [d for d in gdiags if d.level == "error"] == []

    def test_proof_body_not_duplicated(self, single_file_kb: Path):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        topic = single_file_kb / "nodes" / "topic" / "thm"
        canonical_body = parse_file(topic / "canonical.md").body
        cand_a_body = parse_file(topic / "candidates" / "cand_a.md").body
        assert proof_block_start(canonical_body) is None
        assert proof_block_start(cand_a_body) is not None
        # Exactly one proof marker in cand_a.
        assert cand_a_body.count("*Proof.*") == 1

    def test_edge_ownership_and_reachability(self, single_file_kb: Path):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        topic = single_file_kb / "nodes" / "topic" / "thm"
        canonical = parse_file(topic / "canonical.md")
        cand_a = parse_file(topic / "candidates" / "cand_a.md")
        # Canonical delegates all edges to the promoted candidate.
        assert canonical.uses == []
        assert sorted(cand_a.uses) == ["topic.helper_a", "topic.helper_b"]
        # Relaxed criterion #2: reachable deps preserved.
        assert _reachable_deps("topic.thm", single_file_kb) == {
            "topic.helper_a",
            "topic.helper_b",
        }

    def test_canonical_marks_cand_a_promoted(self, single_file_kb: Path):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        topic = single_file_kb / "nodes" / "topic" / "thm"
        canonical = parse_file(topic / "canonical.md")
        cand_a = parse_file(topic / "candidates" / "cand_a.md")
        assert canonical.candidate_layout == "multi"
        assert canonical.promoted_candidate == "cand_a"
        assert sorted(canonical.candidates) == ["cand_a", "cand_b"]
        assert cand_a.status == "promoted"
        assert cand_a.verification is not None
        assert cand_a.verification.proof == "accepted"


class TestSecondSpawn:
    def test_spawn_on_existing_dir_adds_next_slug_without_migration(
        self, single_file_kb: Path
    ):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)  # -> cand_b
        result = spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        assert result.success, result.diagnostics
        assert result.migrated is False
        assert result.new_slug == "cand_c"
        topic = single_file_kb / "nodes" / "topic" / "thm"
        assert (topic / "candidates" / "cand_c.md").exists()
        canonical = parse_file(topic / "canonical.md")
        assert sorted(canonical.candidates) == ["cand_a", "cand_b", "cand_c"]

    def test_explicit_slug_is_used(self, single_file_kb: Path):
        result = spawn_candidate(
            "topic.thm", knowledge_root=single_file_kb, slug="myproof"
        )
        assert result.success, result.diagnostics
        assert result.new_slug == "myproof"
        topic = single_file_kb / "nodes" / "topic" / "thm"
        assert (topic / "candidates" / "myproof.md").exists()

    def test_invalid_slug_rejected(self, single_file_kb: Path):
        result = spawn_candidate(
            "topic.thm", knowledge_root=single_file_kb, slug="Bad-Slug"
        )
        assert not result.success
        assert any("slug" in d.message.lower() for d in result.diagnostics)

    def test_new_candidate_is_unverified_with_placeholder_proof(
        self, single_file_kb: Path
    ):
        spawn_candidate("topic.thm", knowledge_root=single_file_kb)
        cand_b = parse_file(
            single_file_kb / "nodes" / "topic" / "thm" / "candidates" / "cand_b.md"
        )
        assert cand_b.status == "candidate"
        assert cand_b.verification is not None
        assert cand_b.verification.proof != "accepted"
        # New attempt inherits the promoted candidate's dependency baseline.
        assert sorted(cand_b.uses) == ["topic.helper_a", "topic.helper_b"]


class TestSpawnErrors:
    def test_unknown_canonical(self, single_file_kb: Path):
        result = spawn_candidate("topic.nope", knowledge_root=single_file_kb)
        assert not result.success
        assert any("not found" in d.message.lower() or "unknown" in d.message.lower()
                   for d in result.diagnostics)
