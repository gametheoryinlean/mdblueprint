"""Generate static HTML site from knowledge nodes."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
from tools.knowledge.config import LeanConfig, katex_auto_render_options, load_project_config
from tools.knowledge.export import write_graph_json
from tools.knowledge.graph import build_graph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex, index_lean_project
from tools.knowledge.models import Node
from tools.knowledge.parser import scan_directory

TEMPLATE_DIR = Path(__file__).parent / "templates"
PROOF_MARKER_RE = re.compile(r"(?im)(^|\n)(?P<marker>\s*(?:\*{1,2}Proof\.\*{1,2}|Proof\.|##\s+Proof)\s*)")
TEX_MATH_RE = re.compile(
    r"\$\$(?:.|\n)*?\$\$"
    r"|\\\[(?:.|\n)*?\\\]"
    r"|\\\((?:.|\n)*?\\\)"
    r"|(?<!\\)\$(?!\$)(?:\\.|[^\n$\\])+(?<!\\)\$"
)


def _node_href(node_id: str, from_topic: str | None = None) -> str:
    parts = node_id.split(".")
    topic = parts[0] if len(parts) > 1 else "misc"
    filename = node_id.replace(".", "_") + ".html"
    if from_topic == topic:
        return filename
    return f"../{topic}/{filename}" if from_topic else f"{topic}/{filename}"


def _node_href_from_root(node_id: str) -> str:
    parts = node_id.split(".")
    topic = parts[0] if len(parts) > 1 else "misc"
    filename = node_id.replace(".", "_") + ".html"
    return f"{topic}/{filename}"


def _titleize(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _split_proof_markdown(body: str) -> tuple[str, str | None]:
    match = PROOF_MARKER_RE.search(body)
    if match is None:
        return body, None
    statement = body[:match.start()].rstrip()
    proof = body[match.end():].lstrip()
    return statement, proof or None


def _convert_markdown_preserving_tex(md: markdown.Markdown, source: str) -> str:
    replacements: list[tuple[str, str]] = []

    def protect(match: re.Match[str]) -> str:
        token = f"MDBLUEPRINTMATHPLACEHOLDER{len(replacements)}END"
        replacements.append((token, match.group(0)))
        return token

    protected = TEX_MATH_RE.sub(protect, source)
    rendered = md.convert(protected)
    for token, math_source in replacements:
        rendered = rendered.replace(token, escape(math_source, quote=False))
    return rendered


def _render_body(md: markdown.Markdown, body: str) -> dict[str, str | None]:
    statement_md, proof_md = _split_proof_markdown(body)
    md.reset()
    statement_html = _convert_markdown_preserving_tex(md, statement_md)
    proof_html = None
    if proof_md is not None:
        md.reset()
        proof_html = _convert_markdown_preserving_tex(md, proof_md)
    return {
        "body_html": statement_html,
        "proof_html": proof_html,
    }


def _summary_payload(node, blueprint_nodes: dict, href: str) -> dict:
    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "href": href,
        "view": blueprint_nodes[node.id],
    }


def _matching_declarations(decl: str, idx: LeanIndex) -> list[str]:
    if decl in idx.declarations:
        return [decl]
    return [
        qualified
        for qualified in idx.declarations
        if qualified.endswith(f".{decl}") or qualified == decl
    ]


def _module_for_declaration(decl: LeanDeclaration, idx: LeanIndex) -> str | None:
    for module, path in idx.modules.items():
        if path == decl.file:
            return module
    return None


def _lean_ref_payload(
    *,
    name: str,
    status: str,
    qualified_name: str | None = None,
    module: str | None = None,
    repository_title: str | None = None,
    revision: str | None = None,
    source_url: str | None = None,
    has_sorry: bool = False,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "display_name": qualified_name or name,
        "qualified_name": qualified_name,
        "module": module,
        "repository_title": repository_title,
        "revision": revision,
        "short_revision": revision[:7] if revision else None,
        "source_url": source_url,
        "has_sorry": has_sorry,
        "status": status,
        "reason": reason,
    }


def _index_configured_lean_repositories(nodes: list[Node], lean_config: LeanConfig) -> dict[str, LeanIndex]:
    if not lean_config.repositories or not any(node.lean for node in nodes):
        return {}
    return {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in lean_config.repositories.items()
    }


def _resolve_lean_refs(node: Node, lean_config: LeanConfig, indexes: dict[str, LeanIndex]) -> list[dict[str, object]]:
    if node.lean is None:
        return []

    if not indexes:
        return [
            _lean_ref_payload(name=decl, status="raw")
            for decl in node.lean.declarations
        ]

    repo_id = node.lean.repository or lean_config.default_repository
    if repo_id is None:
        return [
            _lean_ref_payload(
                name=decl,
                status="unresolved",
                reason="no Lean repository configured for this node",
            )
            for decl in node.lean.declarations
        ]
    if repo_id not in lean_config.repositories or repo_id not in indexes:
        return [
            _lean_ref_payload(
                name=decl,
                status="unresolved",
                reason=f"Lean repository {repo_id!r} is not configured",
            )
            for decl in node.lean.declarations
        ]

    idx = indexes[repo_id]
    repo = lean_config.repositories[repo_id]
    refs: list[dict[str, object]] = []
    for decl_name in node.lean.declarations:
        matches = _matching_declarations(decl_name, idx)
        if len(matches) == 1:
            decl = idx.declarations[matches[0]]
            refs.append(_lean_ref_payload(
                name=decl_name,
                status="resolved",
                qualified_name=decl.qualified_name,
                module=_module_for_declaration(decl, idx),
                repository_title=decl.repository_title or repo.title,
                revision=decl.revision or repo.revision,
                source_url=decl.source_url,
                has_sorry=decl.has_sorry,
            ))
            continue
        if len(matches) > 1:
            refs.append(_lean_ref_payload(
                name=decl_name,
                status="unresolved",
                reason=f"ambiguous: {', '.join(sorted(matches))}",
            ))
            continue
        refs.append(_lean_ref_payload(
            name=decl_name,
            status="unresolved",
            reason="not found in configured Lean repository",
        ))
    return refs


def publish(knowledge_root: Path, output_dir: Path, config_path: Path | None = None) -> None:
    nodes_dir = knowledge_root / "nodes"
    staged_dir = knowledge_root / "staged"
    config = load_project_config(knowledge_root, config_path)

    all_nodes = []
    if nodes_dir.exists():
        all_nodes.extend(scan_directory(nodes_dir))
    if staged_dir.exists():
        all_nodes.extend(scan_directory(staged_dir))
    lean_indexes = _index_configured_lean_repositories(all_nodes, config.lean)

    g, _ = build_graph(all_nodes)
    blueprint_graph = build_blueprint_graph(g)
    blueprint_dot = graph_to_dot(blueprint_graph)
    blueprint_nodes = {view.id: view for view in blueprint_graph.nodes}
    md = markdown.Markdown(extensions=["tables"])
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["node_href_from_root"] = _node_href_from_root
    env.globals["site"] = config.site
    env.globals["math_options_json"] = json.dumps(katex_auto_render_options(config.math))

    # Group by topic
    topics: dict[str, list] = defaultdict(list)
    for node in all_nodes:
        parts = node.id.split(".")
        topic = parts[0] if len(parts) > 1 else "misc"
        topics[topic].append(node)

    topic_names = sorted(topics.keys())
    keywords: dict[str, list] = defaultdict(list)
    for node in all_nodes:
        for tag in node.tags:
            keywords[tag].append(node)
    keyword_names = sorted(keywords.keys())

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
    shutil.copy(TEMPLATE_DIR / "graph.js", output_dir / "graph.js")

    # Write graph.json
    write_graph_json(g, output_dir / "graph.json")

    node_payloads = {}
    for node in all_nodes:
        parts = node.id.split(".")
        topic = parts[0] if len(parts) > 1 else "misc"

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

        md.reset()
        rendered = _render_body(md, node.body)
        node_payloads[node.id] = {
            "node": node,
            "view": blueprint_nodes[node.id],
            "body_html": rendered["body_html"],
            "proof_html": rendered["proof_html"],
            "deps": deps,
            "dependents": dependents,
            "lean_refs": _resolve_lean_refs(node, config.lean, lean_indexes),
        }

    # Index page
    topic_groups = []
    for topic in topic_names:
        topic_groups.append({
            "name": topic,
            "title": _titleize(topic),
            "href": f"{topic}/index.html",
            "nodes": [
                _summary_payload(node, blueprint_nodes, _node_href(node.id))
                for node in sorted(topics[topic], key=lambda n: n.title)
            ],
        })
    tmpl = env.get_template("index.html")
    (output_dir / "index.html").write_text(
        tmpl.render(
            title="Home",
            root="",
            topics=topic_names,
            keywords=keyword_names,
            topic_groups=topic_groups,
            node_count=len(all_nodes),
            topic_count=len(topic_names),
        ),
        encoding="utf-8",
    )

    # Graph page
    tmpl = env.get_template("graph.html")
    graph_html = tmpl.render(
        title="Dependency graph",
        root="",
        topics=topic_names,
        keywords=keyword_names,
        graph_dot=blueprint_dot,
        graph_nodes=[node_payloads[view.id] for view in blueprint_graph.nodes],
    )
    (output_dir / "dep_graph_document.html").write_text(
        graph_html,
        encoding="utf-8",
    )
    (output_dir / "graph.html").write_text(
        graph_html,
        encoding="utf-8",
    )

    # Keyword pages
    keyword_dir = output_dir / "keywords"
    keyword_dir.mkdir(parents=True, exist_ok=True)
    tmpl = env.get_template("keyword.html")
    for keyword in keyword_names:
        keyword_nodes = sorted(keywords[keyword], key=lambda n: n.title)
        (keyword_dir / f"{keyword}.html").write_text(
            tmpl.render(
                title=f"Keyword: {keyword}",
                root="../",
                topics=topic_names,
                keywords=keyword_names,
                keyword=keyword,
                nodes=[
                    _summary_payload(node, blueprint_nodes, f"../{_node_href(node.id)}")
                    for node in keyword_nodes
                ],
            ),
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
                keywords=keyword_names,
                topic=topic,
                topic_title=_titleize(topic),
                nodes=[
                    _summary_payload(node, blueprint_nodes, node.id.replace(".", "_") + ".html")
                    for node in sorted(topic_nodes, key=lambda n: n.title)
                ],
            ),
            encoding="utf-8",
        )

        # Node pages
        tmpl = env.get_template("node.html")
        for node in topic_nodes:
            payload = node_payloads[node.id]

            filename = node.id.replace(".", "_") + ".html"
            (topic_dir / filename).write_text(
                tmpl.render(
                    title=node.title,
                    root="../",
                    topics=topic_names,
                    keywords=keyword_names,
                    node=node,
                    node_view=payload["view"],
                    body_html=payload["body_html"],
                    proof_html=payload["proof_html"],
                    deps=payload["deps"],
                    dependents=payload["dependents"],
                    lean_refs=payload["lean_refs"],
                ),
                encoding="utf-8",
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
