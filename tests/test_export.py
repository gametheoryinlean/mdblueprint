import json
from pathlib import Path

from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory
from tools.knowledge.export import export_graph_json, write_graph_json

NODES_DIR = Path(__file__).parent / "fixtures" / "generic_knowledge" / "nodes" / "algebra"


class TestExportGraphJson:
    def test_structure(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 4

    def test_node_fields(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert group["title"] == "Group"
        assert group["kind"] == "definition"
        assert group["status"] == "admitted"

    def test_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        edge_pairs = {(e["from"], e["to"]) for e in data["edges"]}
        assert ("algebra.group_homomorphism", "algebra.group") in edge_pairs

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
        assert len(data["nodes"]) == 4

    def test_lean_declarations(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert "Algebra.Group" in group["lean_declarations"]

    def test_reverse_deps(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)
        group = next(n for n in data["nodes"] if n["id"] == "algebra.group")
        assert "algebra.group_homomorphism" in group.get("used_by", [])

    def test_blueprint_dot_uses_dependency_to_dependent_direction(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        view = build_blueprint_graph(g)
        dot = graph_to_dot(view)

        assert '"algebra.group" -> "algebra.group_homomorphism"' in dot

    def test_blueprint_dot_uses_leanblueprint_shapes(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        view = build_blueprint_graph(g)
        dot = graph_to_dot(view)

        assert 'shape="box"' in dot
        assert 'shape="ellipse"' in dot

    def test_existing_graph_json_shape_is_unchanged(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        data = export_graph_json(g)

        assert set(data) == {"nodes", "edges"}
        assert {"from": "algebra.group_homomorphism", "to": "algebra.group"} in data["edges"]
