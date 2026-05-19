import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.config import LeanRepositoryConfig
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.lean_link_candidates import build_candidate_bundle
from tools.knowledge.models import LeanRef, Node


def _repo(path: Path) -> LeanRepositoryConfig:
    return LeanRepositoryConfig(
        id="main",
        title="Private Lean",
        local_path=path,
        web_url="https://github.com/org/private-lean",
        source_url_template="{web_url}/blob/{revision}/{path}#L{line}",
        revision="abc123",
    )


def _index(tmp_path: Path):
    lean_root = tmp_path / "lean"
    (lean_root / "GameTheoryLib" / "StrategicGame").mkdir(parents=True)
    (lean_root / "GameTheoryLib" / "StrategicGame" / "Basic.lean").write_text(
        """
namespace StrategicGame

structure StrategicGame where
  players : Type

def IsNashEquilibrium (G : StrategicGame) : Prop :=
  True

theorem nash_equilibrium_exists : True := True.intro

end StrategicGame
""".strip() + "\n",
        encoding="utf-8",
    )
    (lean_root / "Unrelated.lean").write_text(
        "theorem completely_different : True := True.intro\n",
        encoding="utf-8",
    )
    return index_lean_project(lean_root, repository=_repo(lean_root))


def test_explicit_lean_block_is_top_candidate(tmp_path):
    idx = _index(tmp_path)
    node = Node(
        id="strategic_game.nash_equilibrium",
        title="Nash Equilibrium",
        kind="definition",
        status="admitted",
        lean=LeanRef(
            repository="main",
            modules=["GameTheoryLib.StrategicGame.Basic"],
            declarations=["StrategicGame.IsNashEquilibrium"],
        ),
        body="A Nash equilibrium is a profile where no player can improve.",
    )

    bundle = build_candidate_bundle(node, {"main": idx}, default_repository="main")

    assert bundle["node"]["id"] == node.id
    assert bundle["current_lean"]["declarations"] == ["StrategicGame.IsNashEquilibrium"]
    assert bundle["candidates"][0]["declaration"] == "StrategicGame.IsNashEquilibrium"
    assert bundle["candidates"][0]["rank_reason"] == "existing lean frontmatter"
    assert "def IsNashEquilibrium" in bundle["candidates"][0]["signature"]


def test_name_and_title_matches_are_deterministic_and_bounded(tmp_path):
    idx = _index(tmp_path)
    node = Node(
        id="strategic_game.nash_equilibrium",
        title="Nash Equilibrium",
        kind="theorem",
        status="admitted",
        body="A Nash equilibrium exists.",
    )

    bundle = build_candidate_bundle(node, {"main": idx}, default_repository="main", max_candidates=2)

    assert [c["declaration"] for c in bundle["candidates"]] == [
        "StrategicGame.nash_equilibrium_exists",
        "StrategicGame.IsNashEquilibrium",
    ]
    rendered = json.dumps(bundle)
    assert "completely_different" not in rendered
    assert "Unrelated.lean" not in rendered


def test_no_match_bundle_allows_agent_to_choose_none(tmp_path):
    idx = _index(tmp_path)
    node = Node(
        id="analysis.fixed_point",
        title="Fixed Point Theorem",
        kind="theorem",
        status="admitted",
        body="Every continuous self-map has a fixed point.",
    )

    bundle = build_candidate_bundle(node, {"main": idx}, default_repository="main")

    assert bundle["candidates"] == []
    assert bundle["instructions"]["agent_may_choose_none"] is True


def test_cli_indexes_configured_repo_even_before_node_has_lean_block(tmp_path):
    lean_root = tmp_path / "lean"
    (lean_root / "Example").mkdir(parents=True)
    (lean_root / "Example" / "Basic.lean").write_text(
        "theorem Example.fixed_point_theorem : True := True.intro\n",
        encoding="utf-8",
    )
    knowledge_root = tmp_path / "knowledge"
    node_dir = knowledge_root / "nodes" / "analysis"
    node_dir.mkdir(parents=True)
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Lean Link Candidate Blueprint
            lean:
              default_repository: main
              repositories:
                - id: main
                  title: Private Lean
                  local_path: {lean_root}
                  web_url: https://github.com/org/private-lean
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: abc123
            """
        ).strip(),
        encoding="utf-8",
    )
    (node_dir / "fixed_point.md").write_text(
        textwrap.dedent(
            """
            ---
            id: analysis.fixed_point
            title: Fixed Point Theorem
            kind: theorem
            status: admitted
            uses: []
            verification:
              statement: accepted
              proof: accepted
            ---

            # Fixed Point Theorem

            A fixed point theorem.
            """
        ).strip(),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.lean_link_candidates",
            str(knowledge_root),
            "--node-id",
            "analysis.fixed_point",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    bundle = json.loads(proc.stdout)

    assert bundle["current_lean"] is None
    assert [candidate["declaration"] for candidate in bundle["candidates"]] == [
        "Example.fixed_point_theorem"
    ]
