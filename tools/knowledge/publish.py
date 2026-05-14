"""Generate static HTML site from knowledge nodes."""
from __future__ import annotations

import shutil
import sys
from collections import defaultdict
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tools.knowledge.export import write_graph_json
from tools.knowledge.graph import build_graph
from tools.knowledge.parser import scan_directory

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _node_href(node_id: str, from_topic: str | None = None) -> str:
    parts = node_id.split(".")
    topic = parts[0] if len(parts) > 1 else "misc"
    filename = node_id.replace(".", "_") + ".html"
    if from_topic == topic:
        return filename
    return f"../{topic}/{filename}" if from_topic else f"{topic}/{filename}"


def publish(knowledge_root: Path, output_dir: Path) -> None:
    nodes_dir = knowledge_root / "nodes"
    staged_dir = knowledge_root / "staged"

    all_nodes = []
    if nodes_dir.exists():
        all_nodes.extend(scan_directory(nodes_dir))
    if staged_dir.exists():
        all_nodes.extend(scan_directory(staged_dir))

    g, _ = build_graph(all_nodes)
    md = markdown.Markdown(extensions=["tables"])
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )

    # Group by topic
    topics: dict[str, list] = defaultdict(list)
    for node in all_nodes:
        parts = node.id.split(".")
        topic = parts[0] if len(parts) > 1 else "misc"
        topics[topic].append(node)

    topic_names = sorted(topics.keys())

    # Clean and create output
    resolved_out = output_dir.resolve()
    resolved_root = knowledge_root.resolve()
    if resolved_out == resolved_root or resolved_root.is_relative_to(resolved_out):
        raise ValueError(f"Refusing to delete {output_dir}: would remove source tree")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Copy CSS
    shutil.copy(TEMPLATE_DIR / "style.css", output_dir / "style.css")

    # Write graph.json
    write_graph_json(g, output_dir / "graph.json")

    # Index page
    index_nodes = []
    for node in sorted(all_nodes, key=lambda n: n.id):
        index_nodes.append({
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
            "href": _node_href(node.id),
        })
    tmpl = env.get_template("index.html")
    (output_dir / "index.html").write_text(
        tmpl.render(
            title="Knowledge Base",
            root="",
            topics=topic_names,
            nodes=index_nodes,
            node_count=len(all_nodes),
            topic_count=len(topic_names),
        ),
        encoding="utf-8",
    )

    # Graph page
    tmpl = env.get_template("graph.html")
    (output_dir / "graph.html").write_text(
        tmpl.render(title="DAG View", root="", topics=topic_names),
        encoding="utf-8",
    )

    # Topic pages and node pages
    for topic, topic_nodes in topics.items():
        topic_dir = output_dir / topic
        topic_dir.mkdir(parents=True, exist_ok=True)

        # Topic index
        tmpl = env.get_template("topic.html")
        (topic_dir / "index.html").write_text(
            tmpl.render(
                title=topic,
                root="../",
                topics=topic_names,
                topic=topic,
                nodes=sorted(topic_nodes, key=lambda n: n.id),
            ),
            encoding="utf-8",
        )

        # Node pages
        tmpl = env.get_template("node.html")
        for node in topic_nodes:
            md.reset()
            body_html = md.convert(node.body)

            deps = []
            for dep_id in node.uses:
                dep_node = g.nodes.get(dep_id)
                if dep_node:
                    deps.append({
                        "id": dep_id,
                        "title": dep_node.title,
                        "href": _node_href(dep_id, from_topic=topic),
                    })

            dependents = []
            for rev_id in sorted(g.reverse_edges.get(node.id, [])):
                rev_node = g.nodes.get(rev_id)
                if rev_node:
                    dependents.append({
                        "id": rev_id,
                        "title": rev_node.title,
                        "href": _node_href(rev_id, from_topic=topic),
                    })

            filename = node.id.replace(".", "_") + ".html"
            (topic_dir / filename).write_text(
                tmpl.render(
                    title=node.title,
                    root="../",
                    topics=topic_names,
                    node=node,
                    body_html=body_html,
                    deps=deps,
                    dependents=dependents,
                ),
                encoding="utf-8",
            )


def main() -> None:
    knowledge_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/knowledge")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else knowledge_root / "site"
    publish(knowledge_root, output_dir)
    print(f"Published to {output_dir}")


if __name__ == "__main__":
    main()
