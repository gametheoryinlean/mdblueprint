from pathlib import Path

import pytest

from tools.knowledge.parser import parse_node, parse_file, scan_directory

_TESTS_DIR = Path(__file__).parent
NODES_DIR = _TESTS_DIR.parent / "docs" / "knowledge" / "nodes" / "strategic_games"
STAGED_DIR = _TESTS_DIR.parent / "docs" / "knowledge" / "staged"


class TestParseNode:
    def test_parse_strategic_game(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        assert node.id == "strategic_games.strategic_game"
        assert node.title == "Strategic Game"
        assert node.kind == "definition"
        assert node.status == "admitted"
        assert node.uses == []
        assert node.lean is not None
        assert "StrategicGame" in node.lean.declarations
        assert "GameTheoryLib.StrategicGame.Basic" in node.lean.modules

    def test_parse_source_format(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        assert node.source is not None
        assert len(node.source.artifacts) == 1
        assert node.source.artifacts[0].id == "msz"
        assert "maschler" in node.source.artifacts[0].path
        assert len(node.source.spans) == 1
        assert node.source.spans[0].artifact == "msz"
        assert node.source.spans[0].format == "section"

    def test_parse_verification(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        assert node.verification is not None
        assert node.verification.definition == "accepted"
        assert node.verification.statement is None
        assert node.verification.proof == "not_applicable"

    def test_parse_theorem_verification(self):
        node = parse_file(NODES_DIR / "dominant_implies_nash.md")
        assert node.verification is not None
        assert node.verification.statement == "accepted"
        assert node.verification.definition is None
        assert node.verification.proof == "accepted"

    def test_parse_dependencies(self):
        node = parse_file(NODES_DIR / "nash_equilibrium.md")
        assert "strategic_games.best_response" in node.uses

    def test_parse_generality(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        assert node.generality is not None
        assert node.generality.reviewed is True
        assert node.generality.verdict is not None

    def test_parse_body(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        assert "strategic game" in node.body.lower()
        assert "---" not in node.body

    def test_parse_staged(self):
        node = parse_file(STAGED_DIR / "mixed_strategy.md")
        assert node.status == "staged"
        assert node.verification is None
        assert node.generality is None

    def test_no_frontmatter_raises(self):
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            parse_node("no frontmatter here")

    def test_scan_directory(self):
        nodes = scan_directory(NODES_DIR)
        ids = {n.id for n in nodes}
        assert "strategic_games.strategic_game" in ids
        assert "strategic_games.nash_equilibrium" in ids
        assert len(nodes) == 10
