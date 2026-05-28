"""Regression: graph.json's per-node ``topic`` field must use
``home_topic_for_node``, not the file's parent directory name.

Before issue #159 PR 1, ``export.py`` derived the topic from
``file_path.parent.name``, which silently broke the dir layout
(``nodes/<topic>/<local_id>/canonical.md`` would emit
``topic=<local_id>``) and emitted nonsense ``topic="staged"`` for
staged-root nodes.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from tools.knowledge.export import export_graph_json
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(dedent(body).lstrip(), encoding="utf-8")


def test_canonical_in_dir_layout_carries_topic_not_local_id(tmp_path: Path):
    _write(tmp_path / "nodes" / "ext_games" / "spe" / "canonical.md", """
        ---
        id: ext_games.spe
        title: Subgame Perfect Equilibrium
        kind: theorem
        status: admitted
        candidate_layout: multi
        promoted_candidate: cand_a
        candidates: [cand_a]
        uses: []
        verification:
          statement: accepted
          proof: accepted
        lean:
          modules: [Lib.SPE]
          declarations: [Lib.IsSPE]
        ---

        # Subgame Perfect Equilibrium

        Body.
        """)
    _write(tmp_path / "nodes" / "ext_games" / "spe" / "candidates" / "cand_a.md", """
        ---
        id: ext_games.spe._cand_a
        title: SPE (cand_a)
        kind: theorem
        status: promoted
        candidate_of: ext_games.spe
        candidate_slug: cand_a
        uses: []
        verification:
          statement: accepted
          proof: accepted
        ---

        # SPE (cand_a)

        Body.

        *Proof.* Direct.
        """)

    nodes = scan_directory(tmp_path / "nodes")
    g, _ = build_graph(nodes)
    payload = export_graph_json(g)
    by_id = {n["id"]: n for n in payload["nodes"]}

    assert by_id["ext_games.spe"]["topic"] == "ext_games"
    assert by_id["ext_games.spe._cand_a"]["topic"] == "ext_games"


def test_single_file_node_topic_uses_id_prefix(tmp_path: Path):
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
    nodes = scan_directory(tmp_path / "nodes")
    g, _ = build_graph(nodes)
    payload = export_graph_json(g)
    by_id = {n["id"]: n for n in payload["nodes"]}
    assert by_id["topic.x"]["topic"] == "topic"
