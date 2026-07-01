"""Rendering helpers for mdblueprint static site and dev server."""
from __future__ import annotations

import json
import posixpath
import re
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown

from tools.knowledge.config import LeanConfig, ProjectConfig, katex_auto_render_options
from tools.knowledge.export import (
    home_topic_for_node,
    leaf_topic_ids_for_node,
    topic_path,
    titleize_topic,
)
from tools.knowledge.lean_index import (
    LeanDeclaration,
    LeanIndex,
    build_module_source_metadata,
    index_lean_project,
    suggest_for_unresolved,
)
from tools.knowledge.models import Node
from tools.knowledge.node_refs import NODE_REF_RE

if TYPE_CHECKING:
    from tools.knowledge.context import KnowledgeContext

TEMPLATE_DIR = Path(__file__).parent / "templates"
PROOF_MARKER_RE = re.compile(r"(?im)(^|\n)(?P<marker>\s*(?:\*{1,2}Proof\.\*{1,2}|Proof\.|##\s+Proof)\s*)")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def _short_revision(revision: str | None) -> str | None:
    """Return a display-friendly short revision.

    For hex git SHAs (>=7 hex chars) truncate to 7 chars. For branch
    or tag names (or anything else) return the value unchanged so we
    don't mangle e.g. ``release/v0.1`` into ``release``.
    """
    if revision is None:
        return None
    if _GIT_SHA_RE.match(revision):
        return revision[:7]
    return revision
TEX_MATH_RE = re.compile(
    r"\$\$(?:.|\n)*?\$\$"
    r"|\\\[(?:.|\n)*?\\\]"
    r"|\\\((?:.|\n)*?\\\)"
    r"|(?<!\\)\$(?!\$)(?:\\.|[^\n$\\])+(?<!\\)\$"
)


def _node_href(node_id: str, from_topic: str | None = None) -> str:
    target = _node_href_from_root(node_id)
    if from_topic is None:
        return target
    source_dir = topic_path(from_topic)
    return posixpath.relpath(target, start=source_dir)


def _node_href_for_node(node: Node, from_topic: str | None = None) -> str:
    target = _node_href_from_root_for_node(node)
    if from_topic is None:
        return target
    source_dir = topic_path(from_topic)
    return posixpath.relpath(target, start=source_dir)


def _node_href_from_root(node_id: str) -> str:
    topic = ".".join(node_id.split(".")[:-1]) if "." in node_id else "misc"
    filename = node_id.replace(".", "_") + ".html"
    return f"{topic_path(topic)}/{filename}"


def _node_href_from_root_for_node(node: Node) -> str:
    filename = node.id.replace(".", "_") + ".html"
    return f"{topic_path(home_topic_for_node(node))}/{filename}"


def _root_prefix_for_topic(topic: str) -> str:
    return "../" * len(topic_path(topic).split("/"))


def _titleize(value: str) -> str:
    return titleize_topic(value)


def _build_topic_tree(topic_names: list[str]) -> list[dict]:
    tree: dict[str, dict] = {}
    roots: list[dict] = []
    for topic_id in topic_names:
        parts = topic_id.split(".")
        label = parts[-1].replace("_", " ").title()
        node: dict = {"id": topic_id, "label": label, "children": []}
        tree[topic_id] = node
        if len(parts) == 1:
            roots.append(node)
        else:
            parent_id = ".".join(parts[:-1])
            if parent_id in tree:
                tree[parent_id]["children"].append(node)
    return roots


def _load_topic_catalog(
    knowledge_root: Path, topic_id: str, md: markdown.Markdown
) -> str | None:
    for base in ("nodes", "staged"):
        catalog = knowledge_root / base / topic_path(topic_id) / "topics.md"
        if catalog.exists():
            text = catalog.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("---", 3)
                if end != -1:
                    text = text[end + 3:].lstrip()
            md.reset()
            return _convert_markdown_preserving_tex(md, text)
    return None


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


def _resolve_node_refs_in_html(
    html: str,
    all_nodes: dict[str, Node],
    from_topic: str | None = None,
) -> tuple[str, list[str]]:
    unresolved: list[str] = []

    def _replace(m: re.Match) -> str:
        node_id = m.group(1)
        label_raw = m.group(2)
        node = all_nodes.get(node_id)
        if node is None:
            unresolved.append(node_id)
            display = escape(label_raw or node_id)
            return (
                f'<span class="node-ref unresolved" data-node-id="{escape(node_id)}">'
                f"{display}</span>"
            )
        display = escape(label_raw or node.title)
        href = escape(_node_href(node_id, from_topic=from_topic))
        return (
            f'<a class="node-ref" data-node-id="{escape(node_id)}" href="{href}">'
            f"{display}</a>"
        )

    resolved = NODE_REF_RE.sub(_replace, html)
    return resolved, unresolved


_INLINE_CODE_NODE_REF_RE = re.compile(
    r"<code>([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+)</code>"
)
_PRE_BLOCK_RE = re.compile(r"<pre\b[^>]*>.*?</pre>", flags=re.DOTALL | re.IGNORECASE)
_ANCHOR_BLOCK_RE = re.compile(r"<a\b[^>]*>.*?</a>", flags=re.DOTALL | re.IGNORECASE)


def _autolink_bare_node_refs_in_html(
    html: str,
    all_nodes: dict[str, Node],
    from_topic: str | None = None,
) -> str:
    """Auto-link `<code>some.node.id</code>` spans to their canonical pages.

    Skips content already inside `<pre>` blocks (intentional verbatim code)
    and inside existing `<a>` tags (the explicit `[[node:id]]` syntax has
    already produced those). Unknown ids are left untouched.
    """
    if not all_nodes:
        return html

    masks: list[str] = []

    def _mask(match: re.Match[str]) -> str:
        masks.append(match.group(0))
        return f"\x00AUTOLINKMASK{len(masks) - 1}\x00"

    masked = _PRE_BLOCK_RE.sub(_mask, html)
    masked = _ANCHOR_BLOCK_RE.sub(_mask, masked)

    def _link(match: re.Match[str]) -> str:
        node_id = match.group(1)
        if node_id not in all_nodes:
            return match.group(0)
        href = escape(_node_href(node_id, from_topic=from_topic))
        return (
            f'<a class="node-ref" data-node-id="{escape(node_id)}" '
            f'href="{href}"><code>{escape(node_id)}</code></a>'
        )

    linked = _INLINE_CODE_NODE_REF_RE.sub(_link, masked)

    def _restore(match: re.Match[str]) -> str:
        return masks[int(match.group(1))]

    return re.sub(r"\x00AUTOLINKMASK(\d+)\x00", _restore, linked)


def _render_body(
    md: markdown.Markdown,
    body: str,
    all_nodes: dict[str, Node] | None = None,
    from_topic: str | None = None,
) -> dict[str, str | None]:
    statement_md, proof_md = _split_proof_markdown(body)
    md.reset()
    statement_html = _convert_markdown_preserving_tex(md, statement_md)
    proof_html = None
    if proof_md is not None:
        md.reset()
        proof_html = _convert_markdown_preserving_tex(md, proof_md)
    if all_nodes is not None:
        statement_html, _ = _resolve_node_refs_in_html(statement_html, all_nodes, from_topic)
        statement_html = _autolink_bare_node_refs_in_html(statement_html, all_nodes, from_topic)
        if proof_html is not None:
            proof_html, _ = _resolve_node_refs_in_html(proof_html, all_nodes, from_topic)
            proof_html = _autolink_bare_node_refs_in_html(proof_html, all_nodes, from_topic)
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


def _root_dependency_payload(dep_id: str, g) -> dict | None:
    node = g.nodes.get(dep_id)
    if node is None:
        return None
    return {
        "id": dep_id,
        "title": node.title,
        "href": _node_href_from_root_for_node(node),
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
    kind: str | None = None,
    signature: str | None = None,
    docstring: str | None = None,
    repository_title: str | None = None,
    revision: str | None = None,
    source_url: str | None = None,
    doc_url: str | None = None,
    has_sorry: bool = False,
    reason: str | None = None,
    suggestions: list[str] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "display_name": qualified_name or name,
        "qualified_name": qualified_name,
        "module": module,
        "kind": kind,
        "signature": signature,
        "docstring": docstring,
        "repository_title": repository_title,
        "revision": revision,
        "short_revision": _short_revision(revision),
        "source_url": source_url,
        "doc_url": doc_url,
        "has_sorry": has_sorry,
        "status": status,
        "reason": reason,
        "suggestions": list(suggestions or []),
    }


def _lean_module_payload(
    *,
    name: str,
    status: str,
    repository_title: str | None = None,
    revision: str | None = None,
    source_url: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    """Same shape as `_lean_ref_payload` but for module-level refs."""
    return {
        "name": name,
        "display_name": name,
        "repository_title": repository_title,
        "revision": revision,
        "short_revision": _short_revision(revision),
        "source_url": source_url,
        "status": status,
        "reason": reason,
    }


def _resolve_lean_modules(
    node: Node, lean_config: LeanConfig, indexes: dict[str, LeanIndex]
) -> list[dict[str, object]]:
    """Resolve `node.lean.modules` into clickable source links (line 1).

    Mirrors `_resolve_lean_refs` but operates on module names. Returns
    one payload per module, with status:
    - `resolved` when the module is found in the configured index;
    - `raw` when no repositories are configured (no link);
    - `unresolved` when the repo is missing or module isn't indexed.
    """
    if node.lean is None or not node.lean.modules:
        return []

    if not indexes:
        return [_lean_module_payload(name=mod, status="raw") for mod in node.lean.modules]

    repo_id = node.lean.repository or lean_config.default_repository
    if repo_id is None or repo_id not in lean_config.repositories or repo_id not in indexes:
        reason = (
            "no Lean repository configured for this node"
            if repo_id is None
            else f"Lean repository {repo_id!r} is not configured"
        )
        return [
            _lean_module_payload(name=mod, status="unresolved", reason=reason)
            for mod in node.lean.modules
        ]

    idx = indexes[repo_id]
    repo = lean_config.repositories[repo_id]
    refs: list[dict[str, object]] = []
    for module in node.lean.modules:
        path = idx.modules.get(module)
        if path is None:
            refs.append(
                _lean_module_payload(
                    name=module,
                    status="unresolved",
                    reason=f"module not found in repository {repo_id!r}",
                )
            )
            continue
        meta = build_module_source_metadata(path, repo.local_path, repo)
        refs.append(
            _lean_module_payload(
                name=module,
                status="resolved",
                repository_title=meta["repository_title"] or repo.title,
                revision=meta["revision"] or repo.revision,
                source_url=meta["source_url"],
            )
        )
    return refs


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
                kind=decl.kind,
                signature=decl.signature,
                docstring=decl.docstring,
                repository_title=decl.repository_title or repo.title,
                revision=decl.revision or repo.revision,
                source_url=decl.source_url,
                doc_url=decl.doc_url,
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
            suggestions=suggest_for_unresolved(decl_name, idx),
        ))
    return refs


def build_jinja_env(config: ProjectConfig) -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["node_href_from_root"] = _node_href_from_root
    env.globals["topic_path"] = topic_path
    env.globals["site"] = config.site
    env.globals["math_options_json"] = json.dumps(
        katex_auto_render_options(config.math)
    )
    env.filters["titleize"] = _titleize
    return env


def _build_html_payload(ctx: "KnowledgeContext", node: Node) -> dict:
    topic = home_topic_for_node(node)
    md = Markdown(extensions=["tables"])

    deps = []
    for dep_id in node.uses:
        dep_node = ctx.graph.nodes.get(dep_id)
        if dep_node is not None:
            deps.append({
                "id": dep_id,
                "title": dep_node.title,
                "href": _node_href_for_node(dep_node, from_topic=topic),
            })

    dependents = []
    for rev_id in sorted(ctx.graph.reverse_edges.get(node.id, [])):
        rev_node = ctx.graph.nodes.get(rev_id)
        if rev_node is not None:
            dependents.append({
                "id": rev_id,
                "title": rev_node.title,
                "href": _node_href_for_node(rev_node, from_topic=topic),
            })

    rendered = _render_body(
        md, node.body,
        all_nodes=ctx.nodes_by_id,
        from_topic=topic,
    )

    return {
        "view": ctx.blueprint_nodes[node.id],
        "body_html": rendered["body_html"],
        "proof_html": rendered["proof_html"],
        "deps": deps,
        "dependents": dependents,
        "lean_refs": _resolve_lean_refs(node, ctx.config.lean, ctx.lean_indexes),
        "lean_modules": _resolve_lean_modules(node, ctx.config.lean, ctx.lean_indexes),
    }


def node_detail_payload(ctx: "KnowledgeContext", node_id: str) -> dict:
    node = ctx.nodes_by_id.get(node_id)
    if node is None:
        raise KeyError(node_id)

    html_payload = _build_html_payload(ctx, node)

    deps = [
        p for dep_id in node.uses
        if (p := _root_dependency_payload(dep_id, ctx.graph)) is not None
    ]
    dependents = [
        p for rev_id in sorted(ctx.graph.reverse_edges.get(node.id, []))
        if (p := _root_dependency_payload(rev_id, ctx.graph)) is not None
    ]

    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "href": _node_href_from_root_for_node(node),
        "primary_topic": home_topic_for_node(node),
        "topics": leaf_topic_ids_for_node(node),
        "body_html": html_payload["body_html"],
        "proof_html": html_payload["proof_html"],
        "deps": deps,
        "dependents": dependents,
        "lean_refs": html_payload["lean_refs"],
        "lean_modules": html_payload["lean_modules"],
    }


def render_index(ctx: "KnowledgeContext") -> str:
    topic_groups = []
    for topic in ctx.topic_names:
        topic_groups.append({
            "name": topic,
            "title": _titleize(topic),
            "href": f"{topic_path(topic)}/index.html",
            "nodes": [
                _summary_payload(
                    node, ctx.blueprint_nodes,
                    _node_href_for_node(node),
                )
                for node in sorted(ctx.topics[topic], key=lambda n: n.title)
            ],
        })

    tmpl = ctx.jinja_env.get_template("index.html")
    return tmpl.render(
        title="Home",
        root="",
        topics=ctx.topic_names,
        topic_tree=ctx.topic_tree,
        active_topic="",
        keywords=ctx.keyword_names,
        topic_groups=topic_groups,
        node_count=len(ctx.all_nodes),
        topic_count=len(ctx.topic_names),
        dev_mode=ctx.dev_mode,
    )


def render_graph_page(ctx: "KnowledgeContext") -> str:
    tmpl = ctx.jinja_env.get_template("graph.html")
    return tmpl.render(
        title="Dependency graph",
        root="",
        topics=ctx.topic_names,
        topic_tree=ctx.topic_tree,
        active_topic="",
        keywords=ctx.keyword_names,
        graph_config_json=json.dumps({
            "topicOverviewUrl": "graph_topics.json",
            "topicSubgraphBaseUrl": "subgraphs/topics",
            "maxVisibleNodes": ctx.config.graph.max_visible_nodes,
            "maxExpandNodes": ctx.config.graph.max_expand_nodes,
            "proofPlans": ctx.config.graph.proof_plans,
            "mode": "topic-overview",
        }),
        dev_mode=ctx.dev_mode,
    )


def render_topic(ctx: "KnowledgeContext", topic_id: str) -> str:
    if topic_id not in ctx.topics:
        raise KeyError(topic_id)

    topic_nodes = ctx.topics[topic_id]
    root = _root_prefix_for_topic(topic_id)
    md = Markdown(extensions=["tables"])

    catalog_html = _load_topic_catalog(ctx.knowledge_root, topic_id, md)
    if catalog_html:
        catalog_html, _ = _resolve_node_refs_in_html(
            catalog_html, ctx.nodes_by_id, from_topic=topic_id,
        )
        catalog_html = _autolink_bare_node_refs_in_html(
            catalog_html, ctx.nodes_by_id, from_topic=topic_id,
        )

    status_counts: dict[str, int] = {}
    for n in topic_nodes:
        status_counts[n.status] = status_counts.get(n.status, 0) + 1

    tmpl = ctx.jinja_env.get_template("topic.html")
    return tmpl.render(
        title=topic_id,
        root=root,
        topics=ctx.topic_names,
        topic_tree=ctx.topic_tree,
        active_topic=topic_id,
        keywords=ctx.keyword_names,
        topic=topic_id,
        topic_title=_titleize(topic_id),
        child_topics=ctx.child_topics_map[topic_id],
        catalog_html=catalog_html,
        status_counts=status_counts,
        nodes=[
            _summary_payload(
                node, ctx.blueprint_nodes,
                _node_href_for_node(node, from_topic=topic_id),
            )
            for node in sorted(topic_nodes, key=lambda n: n.title)
        ],
        dev_mode=ctx.dev_mode,
    )


def render_node(ctx: "KnowledgeContext", node_id: str) -> str:
    node = ctx.nodes_by_id.get(node_id)
    if node is None:
        raise KeyError(node_id)

    topic = home_topic_for_node(node)
    root = _root_prefix_for_topic(topic)
    payload = _build_html_payload(ctx, node)
    topic_memberships = leaf_topic_ids_for_node(node)
    child_topics = (
        ctx.child_topics_map.get(node.id, [])
        if node.kind == "topic"
        else []
    )

    tmpl = ctx.jinja_env.get_template("node.html")
    return tmpl.render(
        title=node.title,
        root=root,
        topics=ctx.topic_names,
        topic_tree=ctx.topic_tree,
        active_topic=topic,
        keywords=ctx.keyword_names,
        node=node,
        node_view=payload["view"],
        body_html=payload["body_html"],
        proof_html=payload["proof_html"],
        deps=payload["deps"],
        dependents=payload["dependents"],
        lean_refs=payload["lean_refs"],
        lean_modules=payload["lean_modules"],
        topic_memberships=topic_memberships,
        child_topics=child_topics,
        dev_mode=ctx.dev_mode,
    )


def render_keyword(ctx: "KnowledgeContext", keyword: str) -> str:
    if keyword not in ctx.keywords:
        raise KeyError(keyword)

    keyword_nodes = sorted(ctx.keywords[keyword], key=lambda n: n.title)
    tmpl = ctx.jinja_env.get_template("keyword.html")
    return tmpl.render(
        title=f"Keyword: {keyword}",
        root="../",
        topics=ctx.topic_names,
        topic_tree=ctx.topic_tree,
        active_topic="",
        keywords=ctx.keyword_names,
        keyword=keyword,
        nodes=[
            _summary_payload(
                node, ctx.blueprint_nodes,
                f"../{_node_href_for_node(node)}",
            )
            for node in keyword_nodes
        ],
        dev_mode=ctx.dev_mode,
    )
