from pathlib import Path

from tools.knowledge.graph import build_graph, topological_sort
from tools.knowledge.parser import parse_file, scan_directory

NODES_DIR = Path("docs/knowledge/nodes/strategic_games")
STAGED_DIR = Path("docs/knowledge/staged")
INVALID_DIR = Path("tests/fixtures/invalid")


class TestBuildGraph:
    def test_build_from_admitted_nodes(self):
        nodes = scan_directory(NODES_DIR)
        g, diags = build_graph(nodes)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []
        assert len(g.nodes) == 10

    def test_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        assert "strategic_games.strategy_profile" in g.edges["strategic_games.unilateral_deviation"]

    def test_reverse_edges(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        assert "strategic_games.unilateral_deviation" in g.reverse_edges["strategic_games.strategy_profile"]

    def test_with_staged(self):
        admitted = scan_directory(NODES_DIR)
        staged = scan_directory(STAGED_DIR)
        g, diags = build_graph(admitted + staged)
        assert "strategic_games.mixed_strategy" in g.nodes
        errors = [d for d in diags if d.level == "error"]
        assert errors == []


class TestCycleDetection:
    def test_cycle(self):
        a = parse_file(INVALID_DIR / "cycle_a.md")
        b = parse_file(INVALID_DIR / "cycle_b.md")
        _, diags = build_graph([a, b])
        errors = [d for d in diags if d.level == "error"]
        assert any("cycle" in d.message for d in errors)


class TestDuplicateIds:
    def test_duplicate(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        _, diags = build_graph([node, node])
        errors = [d for d in diags if d.level == "error"]
        assert any("duplicate" in d.message for d in errors)


class TestTaskConstraint:
    def test_math_uses_task(self):
        from tools.knowledge.models import Node
        task = Node(id="test.some_task", title="Task", kind="task", status="admitted")
        math = parse_file(INVALID_DIR / "math_uses_task.md")
        _, diags = build_graph([task, math])
        errors = [d for d in diags if d.level == "error"]
        assert any("task" in d.message for d in errors)


class TestTopologicalSort:
    def test_order(self):
        nodes = scan_directory(NODES_DIR)
        g, _ = build_graph(nodes)
        order = topological_sort(g)
        idx = {nid: i for i, nid in enumerate(order)}
        # strategic_game must come before strategy_profile
        assert idx["strategic_games.strategic_game"] < idx["strategic_games.strategy_profile"]
        # strategy_profile before unilateral_deviation
        assert idx["strategic_games.strategy_profile"] < idx["strategic_games.unilateral_deviation"]
        # best_response before nash_equilibrium
        assert idx["strategic_games.best_response"] < idx["strategic_games.nash_equilibrium"]
