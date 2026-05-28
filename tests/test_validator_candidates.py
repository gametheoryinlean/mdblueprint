"""Cross-file validation for the multi-candidate layout (issue #159, PR 2).

These exercise ``candidate_layout.discover_canonical_groups`` and
``candidate_layout.validate_canonical_groups``: the invariants that span
``canonical.md`` and its sibling ``candidates/*.md`` files.

Per-node schema rules (slug regex, id composition, staged rejection)
live in ``test_models_candidate.py`` and are not re-tested here.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tools.knowledge.candidate_layout import (
    canonical_dir,
    discover_canonical_groups,
    validate_canonical_groups,
)
from tools.knowledge.parser import scan_directory


def _write(p: Path, body: str) -> None:
    # ``body`` is already flush-left (templates are dedented at module load),
    # so we must NOT dedent again — a multi-line injected statement value
    # would otherwise defeat textwrap.dedent's common-prefix calculation.
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.lstrip(), encoding="utf-8")


def _validate(root: Path):
    nodes = scan_directory(root / "nodes")
    nodes_by_id = {n.id: n for n in nodes}
    groups = discover_canonical_groups(nodes)
    return validate_canonical_groups(groups, nodes_by_id)


def _errors(root: Path) -> list[str]:
    return [d.message for d in _validate(root) if d.level == "error"]


# ── Fixture builders ──────────────────────────────────────────────────────────

_CANONICAL = dedent("""
    ---
    id: {cid}
    title: {title}
    kind: theorem
    status: admitted
    candidate_layout: multi
    promoted_candidate: {promoted}
    candidates: {candidates}
    uses: []
    verification:
      statement: accepted
      proof: accepted
    lean:
      modules: [Lib.M]
      declarations: [Lib.D]
    ---

    # {title}

    The statement of the theorem holds for all inputs.
    """)

_CANDIDATE = dedent("""
    ---
    id: {cid}._{slug}
    title: {title}
    kind: {kind}
    status: {status}
    candidate_of: {cid}
    candidate_slug: {slug}
    uses: []
    verification:
      statement: accepted
      proof: {proof}
    ---

    # {title}

    {statement}

    *Proof.* {proof_body}
    """)


def _build(
    tmp_path: Path,
    *,
    topic_segments: tuple[str, ...] = ("ext_games",),
    local_id: str = "spe",
    promoted: str = "cand_a",
    declared_candidates: str = "[cand_a]",
    candidates: tuple[dict, ...] = ({"slug": "cand_a", "status": "promoted"},),
    statement: str = "The statement of the theorem holds for all inputs.",
) -> Path:
    cid = ".".join(topic_segments) + f".{local_id}"
    cdir = tmp_path / "nodes"
    for seg in topic_segments:
        cdir = cdir / seg
    cdir = cdir / local_id
    _write(
        cdir / "canonical.md",
        _CANONICAL.format(
            cid=cid, title="Thm", promoted=promoted, candidates=declared_candidates
        ),
    )
    for c in candidates:
        _write(
            cdir / "candidates" / f"{c['slug']}.md",
            _CANDIDATE.format(
                cid=cid,
                slug=c["slug"],
                title=f"Thm ({c['slug']})",
                kind=c.get("kind", "theorem"),
                status=c["status"],
                proof="accepted" if c["status"] == "promoted" else "gap",
                statement=c.get("statement", statement),
                proof_body="By induction.",
            ),
        )
    return tmp_path


# ── canonical_dir ──────────────────────────────────────────────────────────────

class TestCanonicalDir:
    def test_canonical_dir_for_canonical_and_candidate(self, tmp_path: Path):
        root = _build(tmp_path)
        nodes = {n.id: n for n in scan_directory(root / "nodes")}
        canonical = nodes["ext_games.spe"]
        candidate = nodes["ext_games.spe._cand_a"]
        expected = root / "nodes" / "ext_games" / "spe"
        assert canonical_dir(canonical) == expected
        assert canonical_dir(candidate) == expected

    def test_canonical_dir_nested_topic(self, tmp_path: Path):
        root = _build(tmp_path, topic_segments=("ext_games", "subgames"))
        nodes = {n.id: n for n in scan_directory(root / "nodes")}
        canonical = nodes["ext_games.subgames.spe"]
        candidate = nodes["ext_games.subgames.spe._cand_a"]
        expected = root / "nodes" / "ext_games" / "subgames" / "spe"
        assert canonical_dir(canonical) == expected
        assert canonical_dir(candidate) == expected

    def test_canonical_dir_none_for_plain_node(self):
        from tools.knowledge.models import Node

        n = Node(id="topic.x", title="X", kind="theorem", status="admitted",
                 file_path=Path("nodes/topic/x.md"))
        assert canonical_dir(n) is None


# ── Well-formed groups accept ──────────────────────────────────────────────────

class TestAccepting:
    def test_single_promoted_candidate_accepts(self, tmp_path: Path):
        root = _build(tmp_path)
        assert _errors(root) == []

    def test_nested_topic_accepts(self, tmp_path: Path):
        root = _build(tmp_path, topic_segments=("ext_games", "subgames"))
        assert _errors(root) == []

    def test_promoted_plus_abandoned_accepts(self, tmp_path: Path):
        root = _build(
            tmp_path,
            promoted="cand_a",
            declared_candidates="[cand_a, cand_b]",
            candidates=(
                {"slug": "cand_a", "status": "promoted"},
                {"slug": "cand_b", "status": "abandoned"},
            ),
        )
        assert _errors(root) == []

    def test_no_promoted_yet_accepts(self, tmp_path: Path):
        root = _build(
            tmp_path,
            promoted="null",
            declared_candidates="[cand_a]",
            candidates=({"slug": "cand_a", "status": "candidate"},),
        )
        assert _errors(root) == []


# ── Cross-file rejections ───────────────────────────────────────────────────────

class TestRejecting:
    def test_unknown_canonical(self, tmp_path: Path):
        # A candidate file whose canonical.md is absent.
        cdir = tmp_path / "nodes" / "ext_games" / "spe"
        _write(cdir / "candidates" / "cand_a.md", _CANDIDATE.format(
            cid="ext_games.spe", slug="cand_a", title="Orphan", kind="theorem",
            status="candidate", proof="gap",
            statement="Body.", proof_body="x",
        ))
        msgs = " ".join(_errors(tmp_path))
        assert "canonical" in msgs.lower()

    def test_candidate_of_points_to_single_file_node(self, tmp_path: Path):
        # canonical exists but is NOT multi-layout (single-file form).
        _write(tmp_path / "nodes" / "ext_games" / "spe.md", dedent("""
            ---
            id: ext_games.spe
            title: Thm
            kind: theorem
            status: admitted
            uses: []
            verification:
              statement: accepted
              proof: accepted
            lean:
              modules: [Lib.M]
              declarations: [Lib.D]
            ---

            # Thm

            Body.

            *Proof.* Direct.
            """))
        _write(tmp_path / "nodes" / "ext_games" / "spe" / "candidates" / "cand_a.md",
               _CANDIDATE.format(
                   cid="ext_games.spe", slug="cand_a", title="C", kind="theorem",
                   status="candidate", proof="gap", statement="Body.", proof_body="x",
               ))
        msgs = " ".join(_errors(tmp_path))
        assert "multi" in msgs.lower() or "canonical.md" in msgs.lower()

    def test_candidates_field_mismatch(self, tmp_path: Path):
        root = _build(
            tmp_path,
            declared_candidates="[cand_a, cand_b]",  # claims cand_b but no file
            candidates=({"slug": "cand_a", "status": "promoted"},),
        )
        msgs = " ".join(_errors(root))
        assert "candidates" in msgs.lower()

    def test_two_promoted_siblings(self, tmp_path: Path):
        root = _build(
            tmp_path,
            promoted="cand_a",
            declared_candidates="[cand_a, cand_b]",
            candidates=(
                {"slug": "cand_a", "status": "promoted"},
                {"slug": "cand_b", "status": "promoted"},
            ),
        )
        msgs = " ".join(_errors(root))
        assert "promoted" in msgs.lower()

    def test_promoted_candidate_names_unknown_slug(self, tmp_path: Path):
        root = _build(
            tmp_path,
            promoted="cand_x",
            declared_candidates="[cand_a]",
            candidates=({"slug": "cand_a", "status": "promoted"},),
        )
        msgs = " ".join(_errors(root))
        assert "promoted_candidate" in msgs.lower()

    def test_promoted_candidate_null_but_sibling_promoted(self, tmp_path: Path):
        root = _build(
            tmp_path,
            promoted="null",
            declared_candidates="[cand_a]",
            candidates=({"slug": "cand_a", "status": "promoted"},),
        )
        msgs = " ".join(_errors(root))
        assert "promoted" in msgs.lower()

    def test_statement_divergence(self, tmp_path: Path):
        root = _build(
            tmp_path,
            candidates=(
                {"slug": "cand_a", "status": "promoted",
                 "statement": "A completely different statement body."},
            ),
        )
        msgs = " ".join(_errors(root))
        assert "statement" in msgs.lower()

    def test_kind_mismatch(self, tmp_path: Path):
        root = _build(
            tmp_path,
            candidates=(
                {"slug": "cand_a", "status": "promoted", "kind": "lemma"},
            ),
        )
        msgs = " ".join(_errors(root))
        assert "kind" in msgs.lower()


class TestStatementNormalisation:
    def test_whitespace_and_trailing_punct_ignored(self, tmp_path: Path):
        root = _build(
            tmp_path,
            statement="The statement of the theorem holds for all inputs.",
            candidates=(
                {"slug": "cand_a", "status": "promoted",
                 "statement": "The   statement of the theorem\nholds for all inputs"},
            ),
        )
        assert _errors(root) == []
