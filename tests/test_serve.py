import json
import shutil
import threading
from pathlib import Path

import pytest

from tools.knowledge.serve import DevServer

KNOWLEDGE_ROOT = Path(__file__).parent.parent / "docs" / "knowledge"


@pytest.fixture
def server():
    s = DevServer(KNOWLEDGE_ROOT, port=0)
    yield s


@pytest.fixture
def client(server):
    app = server.make_app()
    app.config["TESTING"] = True
    return app.test_client()


class TestSpecificRoutes:
    def test_index(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"<title>" in r.data

    def test_index_html_alias(self, client):
        assert client.get("/index.html").status_code == 200

    def test_graph_html(self, client):
        r = client.get("/graph.html")
        assert r.status_code == 200
        assert b"Dependency graph" in r.data

    def test_dep_graph_document_alias(self, client):
        assert client.get("/dep_graph_document.html").status_code == 200

    def test_style_css(self, client):
        r = client.get("/style.css")
        assert r.status_code == 200
        assert r.mimetype == "text/css"

    def test_graph_js(self, client):
        r = client.get("/graph.js")
        assert r.status_code == 200
        assert r.mimetype == "application/javascript"

    def test_graph_json(self, client):
        r = client.get("/graph.json")
        assert r.status_code == 200
        assert "nodes" in json.loads(r.data)

    def test_graph_topics_json(self, client):
        r = client.get("/graph_topics.json")
        assert r.status_code == 200
        assert "topics" in json.loads(r.data)

    def test_subgraph_json(self, client):
        r = client.get("/subgraphs/topics/strategic_games.json")
        assert r.status_code == 200
        assert "topic" in json.loads(r.data)

    def test_node_payload_json(self, client):
        r = client.get("/node_payloads/strategic_games_nash_equilibrium.json")
        assert r.status_code == 200
        assert json.loads(r.data)["id"] == "strategic_games.nash_equilibrium"


class TestCatchAll:
    def test_topic_index(self, client):
        assert client.get("/strategic_games/index.html").status_code == 200

    def test_node_page(self, client):
        r = client.get(
            "/strategic_games/strategic_games_nash_equilibrium.html"
        )
        assert r.status_code == 200
        assert b"Nash" in r.data


class TestNotFound:
    def test_unknown_topic(self, client):
        assert client.get("/nope/index.html").status_code == 404

    def test_unknown_node(self, client):
        assert client.get(
            "/strategic_games/does_not_exist.html"
        ).status_code == 404

    def test_unknown_payload(self, client):
        assert client.get("/node_payloads/garbage.json").status_code == 404

    def test_unknown_subgraph(self, client):
        assert client.get("/subgraphs/topics/nope.json").status_code == 404

    def test_unknown_keyword(self, client):
        assert client.get("/keywords/no_such_tag.html").status_code == 404


class TestContextRefresh:
    def test_on_change_swaps_ctx(self, tmp_path):
        shutil.copytree(KNOWLEDGE_ROOT, tmp_path / "kb")
        s = DevServer(tmp_path / "kb", port=0)
        old_ctx = s.ctx
        target = tmp_path / "kb" / "nodes" / "strategic_games" / "nash_equilibrium.md"
        target.write_text(target.read_text().replace(
            "Nash Equilibrium", "Nash Equilibrium MARK"
        ))
        s._on_change()
        assert s.ctx is not old_ctx
        assert "Nash Equilibrium MARK" in s.ctx.nodes_by_id[
            "strategic_games.nash_equilibrium"
        ].title

    def test_on_change_failure_keeps_old_ctx(self, tmp_path, capsys):
        shutil.copytree(KNOWLEDGE_ROOT, tmp_path / "kb")
        s = DevServer(tmp_path / "kb", port=0)
        old_ctx = s.ctx
        (tmp_path / "kb" / "mdblueprint.yml").write_text("not: [valid yaml")
        s._on_change()
        assert s.ctx is old_ctx
        assert "reload failed" in capsys.readouterr().err


class TestSSE:
    def test_change_broadcast_reaches_client(self):
        s = DevServer(KNOWLEDGE_ROOT, port=0)
        q1 = s._register_sse_client()
        q2 = s._register_sse_client()
        s._broadcast_reload()
        assert q1.get(timeout=1.0) == "reload"
        assert q2.get(timeout=1.0) == "reload"

    def test_multiple_changes_all_observed(self):
        s = DevServer(KNOWLEDGE_ROOT, port=0)
        q = s._register_sse_client()
        s._broadcast_reload()
        s._broadcast_reload()
        s._broadcast_reload()
        for _ in range(3):
            assert q.get(timeout=1.0) == "reload"

    def test_unregister_removes_client(self):
        s = DevServer(KNOWLEDGE_ROOT, port=0)
        q = s._register_sse_client()
        assert len(s._sse_clients) == 1
        s._unregister_sse_client(q)
        assert len(s._sse_clients) == 0


class TestConcurrency:
    def test_concurrent_requests_all_succeed(self, client):
        errors: list[Exception] = []
        def hammer():
            try:
                for _ in range(20):
                    assert client.get("/").status_code == 200
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=hammer) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


class TestCLI:
    def test_parses_positional_and_flags(self, tmp_path, monkeypatch):
        called: dict = {}
        class FakeServer:
            def __init__(self, root, *, port, lean):
                called["root"] = root
                called["port"] = port
                called["lean"] = lean
            def run(self):
                called["ran"] = True
        monkeypatch.setattr("tools.knowledge.serve.DevServer", FakeServer)
        from tools.knowledge.serve import main
        main([str(tmp_path), "--port", "9000", "--lean"])
        assert called["root"] == tmp_path
        assert called["port"] == 9000
        assert called["lean"] is True
        assert called["ran"]

    def test_defaults(self, tmp_path, monkeypatch):
        called: dict = {}
        class FakeServer:
            def __init__(self, root, *, port, lean):
                called["port"] = port
                called["lean"] = lean
            def run(self):
                pass
        monkeypatch.setattr("tools.knowledge.serve.DevServer", FakeServer)
        from tools.knowledge.serve import main
        main([str(tmp_path)])
        assert called["port"] == 8080
        assert called["lean"] is False

    def test_missing_positional_exits(self, capsys):
        from tools.knowledge.serve import main
        with pytest.raises(SystemExit):
            main([])
        captured = capsys.readouterr()
        assert "knowledge_root" in captured.err or "required" in captured.err

    def test_invalid_port_exits(self, tmp_path):
        from tools.knowledge.serve import main
        with pytest.raises(SystemExit):
            main([str(tmp_path), "--port", "not-a-number"])