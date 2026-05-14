import json
from pathlib import Path

from tools.knowledge.publish import publish

KNOWLEDGE_ROOT = Path("docs/knowledge")


class TestPublish:
    def test_generates_output(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        assert (site / "index.html").exists()
        assert (site / "graph.html").exists()
        assert (site / "graph.json").exists()
        assert (site / "style.css").exists()

    def test_topic_directory(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        assert (site / "strategic_games" / "index.html").exists()

    def test_node_pages(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        sg_page = site / "strategic_games" / "strategic_games_strategic_game.html"
        assert sg_page.exists()
        content = sg_page.read_text()
        assert "Strategic Game" in content
        assert "StrategicGame" in content

    def test_dependencies_listed(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        ne_page = site / "strategic_games" / "strategic_games_nash_equilibrium.html"
        content = ne_page.read_text()
        assert "best_response" in content

    def test_reverse_deps_listed(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        site = tmp_path / "site"
        br_page = site / "strategic_games" / "strategic_games_best_response.html"
        content = br_page.read_text()
        assert "nash_equilibrium" in content

    def test_graph_json_valid(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        data = json.loads((tmp_path / "site" / "graph.json").read_text())
        assert len(data["nodes"]) >= 10

    def test_index_lists_all(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "strategic_games.strategic_game" in content
        assert "strategic_games.nash_equilibrium" in content

    def test_status_badges(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "status-admitted" in content

    def test_math_rendering_script(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        sg_page = (tmp_path / "site" / "strategic_games" / "strategic_games_strategic_game.html")
        content = sg_page.read_text()
        assert "MathJax" in content

    def test_staged_included(self, tmp_path):
        publish(KNOWLEDGE_ROOT, tmp_path / "site")
        content = (tmp_path / "site" / "index.html").read_text()
        assert "mixed_strategy" in content
