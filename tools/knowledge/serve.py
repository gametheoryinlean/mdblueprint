"""Local dev server for mdblueprint.

Mirrors the static site URL structure so the existing Jinja templates work
without modification. Watches the knowledge root and rebuilds the in-memory
context whenever a `.md` or `.yml` file changes. Pushes SSE `reload` events
to any open browser tab.
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
from pathlib import Path
from flask import Flask, Response, abort, stream_with_context

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.export import (
    export_graph_json,
    export_topic_hierarchy_json,
    export_topic_overview_json,
    export_topic_subgraph_json,
)
from tools.knowledge.renderer import (
    TEMPLATE_DIR,
    node_detail_payload,
    render_graph_page,
    render_index,
    render_keyword,
    render_node,
    render_topic,
)
from tools.knowledge.watcher import KnowledgeWatcher


class DevServer:
    """Stateful dev server holding context, watcher, and SSE client queues."""

    def __init__(
        self,
        knowledge_root: Path,
        *,
        port: int = 8080,
        lean: bool = False,
    ):
        self._root = knowledge_root
        self._port = port
        self._lean = lean
        self._ctx_lock = threading.RLock()
        self._ctx = KnowledgeContext.load(
            knowledge_root, lean=lean, dev_mode=True,
        )
        self._sse_clients: list[queue.Queue[str]] = []
        self._sse_lock = threading.Lock()
        self._watcher = KnowledgeWatcher(knowledge_root, self._on_change)

    @property
    def ctx(self) -> KnowledgeContext:
        with self._ctx_lock:
            return self._ctx

    def _on_change(self) -> None:
        try:
            new_ctx = KnowledgeContext.load(
                self._root, lean=self._lean, dev_mode=True,
            )
        except Exception as exc:
            print(
                f"[mdblueprint-serve] reload failed: {exc!r}",
                file=sys.stderr,
            )
            return
        with self._ctx_lock:
            self._ctx = new_ctx
        self._broadcast_reload()

    def _register_sse_client(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue()
        with self._sse_lock:
            self._sse_clients.append(q)
        return q

    def _unregister_sse_client(self, q: queue.Queue[str]) -> None:
        with self._sse_lock:
            try:
                self._sse_clients.remove(q)
            except ValueError:
                pass

    def _broadcast_reload(self) -> None:
        with self._sse_lock:
            clients = list(self._sse_clients)
        for q in clients:
            q.put("reload")

    def make_app(self) -> Flask:
        app = Flask(__name__)
        server = self

        @app.get("/")
        def root_index():
            return render_index(server.ctx)

        @app.get("/index.html")
        def index_html():
            return render_index(server.ctx)

        @app.get("/graph.html")
        @app.get("/dep_graph_document.html")
        def graph_page():
            return render_graph_page(server.ctx)

        @app.get("/style.css")
        def style_css():
            return Response(
                (TEMPLATE_DIR / "style.css").read_bytes(),
                mimetype="text/css",
            )

        @app.get("/graph.js")
        def graph_js():
            return Response(
                (TEMPLATE_DIR / "graph.js").read_bytes(),
                mimetype="application/javascript",
            )

        @app.get("/graph.json")
        def graph_json():
            return _json_response(export_graph_json(server.ctx.graph))

        @app.get("/graph_topics.json")
        def graph_topics_json():
            return _json_response(export_topic_overview_json(server.ctx.graph))

        @app.get("/graph_topics_hierarchy.json")
        def graph_hierarchy_json():
            return _json_response(export_topic_hierarchy_json(server.ctx.graph))

        @app.get("/subgraphs/topics/<topic_id>.json")
        def subgraph_json(topic_id: str):
            ctx = server.ctx
            if topic_id not in ctx.topics:
                abort(404)
            return _json_response(
                export_topic_subgraph_json(ctx.graph, topic_id, graph_config=ctx.config.graph)
            )

        @app.get("/node_payloads/<node_filename>.json")
        def node_payload_json(node_filename: str):
            ctx = server.ctx
            node_id = ctx.filename_to_node_id.get(node_filename)
            if node_id is None:
                abort(404)
            return _json_response(node_detail_payload(ctx, node_id))

        @app.get("/keywords/<keyword>.html")
        def keyword_page(keyword: str):
            ctx = server.ctx
            if keyword not in ctx.keywords:
                abort(404)
            return render_keyword(ctx, keyword)

        @app.get("/_dev/events")
        def dev_events():
            q = server._register_sse_client()

            def stream():
                try:
                    yield ": connected\n\n"
                    while True:
                        try:
                            msg = q.get(timeout=30.0)
                            yield f"event: reload\ndata: {msg}\n\n"
                        except queue.Empty:
                            yield ": heartbeat\n\n"
                finally:
                    server._unregister_sse_client(q)

            return Response(
                stream_with_context(stream()),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        @app.get("/<path:rest>")
        def catch_all(rest: str):
            ctx = server.ctx
            parts = rest.split("/")
            last = parts[-1]

            if last == "index.html":
                topic_id = ".".join(parts[:-1])
                if topic_id and topic_id in ctx.topics:
                    return render_topic(ctx, topic_id)
                abort(404)

            if last.endswith(".html"):
                stem = last.removesuffix(".html")
                node_id = ctx.filename_to_node_id.get(stem)
                if node_id is not None:
                    return render_node(ctx, node_id)

            abort(404)

        return app

    def run(self) -> None:
        self._watcher.start()
        print(f"Serving at http://localhost:{self._port}")
        print(f"Watching {self._root}")
        try:
            app = self.make_app()
            app.run(
                host="127.0.0.1",
                port=self._port,
                threaded=True,
                use_reloader=False,
                debug=False,
            )
        finally:
            self._watcher.stop()


def _json_response(data) -> Response:
    return Response(
        json.dumps(data, ensure_ascii=False),
        mimetype="application/json",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="mdblueprint local dev server"
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--lean", action="store_true",
                        help="Also build Lean indexes (slower startup)")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    DevServer(args.knowledge_root, port=args.port, lean=args.lean).run()


if __name__ == "__main__":
    main()