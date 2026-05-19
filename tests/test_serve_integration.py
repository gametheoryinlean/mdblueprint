"""End-to-end integration test for the dev server.

Exercises the full chain: file write -> watcher fires -> context rebuilds ->
SSE broadcasts reload -> next HTTP request serves new content.

Marked @pytest.mark.integration so unit-test runs can skip it.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from tools.knowledge.serve import DevServer

KNOWLEDGE_ROOT = Path(__file__).parent.parent / "docs" / "knowledge"


@pytest.fixture
def live_server(tmp_path: Path):
    shutil.copytree(KNOWLEDGE_ROOT, tmp_path / "kb")
    s = DevServer(tmp_path / "kb", port=0)
    s._watcher.start()
    yield s, tmp_path / "kb"
    s._watcher.stop()


@pytest.mark.integration
class TestFullLoop:
    def test_file_change_propagates_to_request(self, live_server):
        s, root = live_server
        app = s.make_app()
        app.config["TESTING"] = True
        client = app.test_client()

        r1 = client.get("/")
        assert r1.status_code == 200
        assert b"INTEGRATION_MARKER" not in r1.data

        sse_q = s._register_sse_client()

        target = root / "nodes" / "strategic_games" / "nash_equilibrium.md"
        target.write_text(
            target.read_text().replace(
                "Nash Equilibrium", "INTEGRATION_MARKER"
            )
        )

        msg = sse_q.get(timeout=5.0)
        assert msg == "reload"

        r2 = client.get("/")
        assert b"INTEGRATION_MARKER" in r2.data

    def test_file_change_invalidates_node_payload(self, live_server):
        s, root = live_server
        app = s.make_app()
        app.config["TESTING"] = True
        client = app.test_client()

        url = "/node_payloads/strategic_games_nash_equilibrium.json"
        before = client.get(url).get_json()
        sse_q = s._register_sse_client()

        target = root / "nodes" / "strategic_games" / "nash_equilibrium.md"
        target.write_text(
            target.read_text().replace(
                "Nash Equilibrium", "PAYLOAD_INTEGRATION_MARKER"
            )
        )
        sse_q.get(timeout=5.0)

        after = client.get(url).get_json()
        assert before["title"] != after["title"]
        assert "PAYLOAD_INTEGRATION_MARKER" in after["title"]

    def test_failed_reload_does_not_break_subsequent_requests(self, live_server):
        s, root = live_server
        app = s.make_app()
        app.config["TESTING"] = True
        client = app.test_client()

        (root / "mdblueprint.yml").write_text("not: [valid yaml")
        time.sleep(1.0)

        r = client.get("/")
        assert r.status_code == 200