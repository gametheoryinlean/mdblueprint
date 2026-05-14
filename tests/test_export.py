import json
from pathlib import Path

from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory
from tools.knowledge.export import export_graph_json, write_graph_json

NODES_DIR = Path(__file__).parent.parent / "docs" / "knowledge" / "nodes" / "strategic_games"


class TestExportGraphJson:
    def test_structure(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 10

    def test_node_fields(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        sg = next(n for n in data["nodes"] if n["id"] == "strategic_games.strategic_game")
        assert sg["title"] == "Strategic Game"
        assert sg["kind"] == "definition"
        assert sg["status"] == "admitted"

    def test_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        edge_pairs = {(e["from"], e["to"]) for e in data["edges"]}
        assert ("strategic_games.strategy_profile", "strategic_games.strategic_game") in edge_pairs

    def test_deterministic(self):
        nodes = scan_directory(NODES_DIR)
        g1, _ = build_graph(nodes)
        g2, _ = build_graph(nodes)
        d1 = json.dumps(export_graph_json(g1), sort_keys=True)
        d2 = json.dumps(export_graph_json(g2), sort_keys=True)
        assert d1 == d2

    def test_write_file(self, tmp_path):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        out = tmp_path / "graph.json"
        write_graph_json(g, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert len(data["nodes"]) == 10

    def test_lean_declarations(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        sg = next(n for n in data["nodes"] if n["id"] == "strategic_games.strategic_game")
        assert "StrategicGame" in sg["lean_declarations"]

    def test_reverse_deps(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        sg = next(n for n in data["nodes"] if n["id"] == "strategic_games.strategic_game")
        assert "strategic_games.strategy_profile" in sg.get("used_by", [])
