"""Generate static HTML site from knowledge nodes."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.export import (
    home_topic_for_node,
    topic_path,
    write_graph_json,
    write_topic_overview_json,
    write_topic_hierarchy_json,
    write_topic_subgraph_jsons,
)
from tools.knowledge.renderer import (
    _build_topic_tree,
    _convert_markdown_preserving_tex,
    node_detail_payload,
    render_graph_page,
    render_index,
    render_keyword,
    render_node,
    render_topic,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def publish(knowledge_root: Path, output_dir: Path, config_path: Path | None = None) -> None:
    ctx = KnowledgeContext.load(
        knowledge_root,
        lean=True,
        dev_mode=False,
        config_path=config_path,
    )

    all_nodes = ctx.all_nodes
    all_nodes_index = ctx.nodes_by_id
    g = ctx.graph
    blueprint_nodes = ctx.blueprint_nodes
    config = ctx.config
    lean_indexes = ctx.lean_indexes
    topics = ctx.topics
    topic_names = ctx.topic_names
    topic_tree = ctx.topic_tree
    child_topics_map = ctx.child_topics_map
    keywords = ctx.keywords
    keyword_names = ctx.keyword_names
    env = ctx.jinja_env

    resolved_out = output_dir.resolve()
    resolved_root = knowledge_root.resolve()
    if resolved_out == resolved_root or resolved_root.is_relative_to(resolved_out):
        raise ValueError(f"Refusing to delete {output_dir}: would remove source tree")
    if resolved_out.is_relative_to(resolved_root) and resolved_out != resolved_root:
        raise ValueError(
            f"Refusing to publish into {output_dir}: output directory is inside the knowledge source tree "
            f"{knowledge_root}. Use a directory outside the knowledge root (e.g. /tmp/mdblueprint-site). "
            "The check command and publish command support an explicit output_dir argument."
        )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    shutil.copy(TEMPLATE_DIR / "style.css", output_dir / "style.css")
    shutil.copy(TEMPLATE_DIR / "graph.js", output_dir / "graph.js")

    write_graph_json(g, output_dir / "graph.json")
    write_topic_overview_json(g, output_dir / "graph_topics.json")
    write_topic_hierarchy_json(g, output_dir / "graph_topics_hierarchy.json")
    write_topic_subgraph_jsons(
        g, output_dir / "subgraphs" / "topics", graph_config=config.graph
    )

    payload_dir = output_dir / "node_payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    for node in all_nodes:
        detail = node_detail_payload(ctx, node.id)
        (payload_dir / f"{node.id.replace('.', '_')}.json").write_text(
            json.dumps(detail, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    (output_dir / "index.html").write_text(render_index(ctx), encoding="utf-8")

    graph_html = render_graph_page(ctx)
    (output_dir / "dep_graph_document.html").write_text(graph_html, encoding="utf-8")
    (output_dir / "graph.html").write_text(graph_html, encoding="utf-8")

    keyword_dir = output_dir / "keywords"
    keyword_dir.mkdir(parents=True, exist_ok=True)
    for keyword in keyword_names:
        (keyword_dir / f"{keyword}.html").write_text(
            render_keyword(ctx, keyword), encoding="utf-8",
        )

    for topic, topic_nodes in topics.items():
        topic_dir = output_dir / topic_path(topic)
        topic_dir.mkdir(parents=True, exist_ok=True)

        (topic_dir / "index.html").write_text(
            render_topic(ctx, topic), encoding="utf-8",
        )

        for node in topic_nodes:
            if home_topic_for_node(node) != topic:
                continue
            filename = node.id.replace(".", "_") + ".html"
            (topic_dir / filename).write_text(
                render_node(ctx, node.id), encoding="utf-8",
            )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Publish mdblueprint static site.")
    parser.add_argument("knowledge_root", nargs="?", type=Path, default=Path("docs/knowledge"))
    parser.add_argument("output_dir", nargs="?", type=Path)
    parser.add_argument("--config", type=Path, help="Project config path; defaults to <knowledge_root>/mdblueprint.yml if present.")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    knowledge_root = args.knowledge_root
    output_dir = args.output_dir if args.output_dir is not None else knowledge_root / "site"
    publish(knowledge_root, output_dir, config_path=args.config)
    print(f"Published to {output_dir}")


if __name__ == "__main__":
    main()
