"""Definition navigation is deterministic and independent of proof edges."""
import json
from pathlib import Path

import pytest
import yaml

from tools.knowledge.check import check_knowledge_base
from tools.knowledge.context import KnowledgeContext
from tools.knowledge.models import Node
from tools.knowledge.publish import publish
from tools.knowledge.renderer import (
    _autolink_bare_node_refs_in_html, _resolve_node_refs_in_html,
    node_detail_payload, render_node, render_topic,
)


def write_node(root: Path, node_id: str, topic: str, kind: str, body: str):
    directory = root / "nodes" / topic
    directory.mkdir(parents=True, exist_ok=True)
    metadata = dict(id=node_id, title=node_id, kind=kind, status="admitted", primary_topic=topic)
    (directory / (node_id + ".md")).write_text(
        "---\n" + yaml.safe_dump(metadata) + "---\n" + body, encoding="utf-8"
    )


@pytest.fixture
def kb(tmp_path):
    root = tmp_path / "knowledge"
    write_node(root, "old.bar", "book.definitions", "definition", "bar involution")
    write_node(root, "old.quadratic", "book.definitions", "definition", "quadratic relation")
    write_node(root, "old.application", "book.chapter", "concept",
               "A bar involution uses the quadratic\nrelation. See [[node:old.bar]].\n\n"
               "## Proof\nThe bar involution.\n")
    guide = root / "nodes" / "book" / "chapter" / "topics.md"
    guide.parent.mkdir(parents=True)
    guide.write_text("A bar involution uses a quadratic relation.\n")
    (root / "concept-links.yml").write_text(yaml.safe_dump({"concepts": [
        {"node": "old.bar", "terms": ["bar involution"]},
        {"node": "old.quadratic", "terms": ["quadratic relation"], "topics": ["book.chapter"]},
    ]}))
    return root


def test_node_reference_uses_primary_topic():
    node = Node(id="old.bar", title="Bar", kind="definition", status="admitted",
                primary_topic="book.definitions")
    explicit, missing = _resolve_node_refs_in_html("[[node:old.bar]]", {node.id: node}, "book.chapter")
    bare = _autolink_bare_node_refs_in_html("<code>old.bar</code>", {node.id: node}, "book.chapter")
    assert not missing
    for html in (explicit, bare):
        assert 'href="../definitions/old_bar.html"' in html


def test_publish_links_plain_prose_and_root_relative_graph_details(kb, tmp_path):
    site = tmp_path / "site"
    publish(kb, site)
    chapter = (site / "book/chapter/index.html").read_text()
    node = (site / "book/chapter/old_application.html").read_text()
    payload = json.loads((site / "node_payloads/old_application.json").read_text())
    for html in (chapter, node):
        assert 'class="node-ref definition-ref"' in html
        assert 'href="../definitions/old_bar.html"' in html
        assert 'href="../definitions/old_quadratic.html"' in html
    for html in (payload["body_html"], payload["proof_html"]):
        assert 'href="book/definitions/old_bar.html"' in html
        assert "../definitions/" not in html
    assert payload["deps"] == []


def test_self_references_and_topic_scope(kb):
    ctx = KnowledgeContext.load(kb)
    assert 'definition-ref' not in node_detail_payload(ctx, "old.bar")["body_html"]
    assert 'definition-ref' not in node_detail_payload(ctx, "old.quadratic")["body_html"]
    assert 'definition-ref' in render_topic(ctx, "book.chapter")


def test_registry_is_optional_and_contexts_are_isolated(kb, tmp_path):
    configured = KnowledgeContext.load(kb)
    other = tmp_path / "other"
    write_node(other, "old.application", "book.chapter", "concept", "bar involution")
    unconfigured = KnowledgeContext.load(other)
    assert "definition-ref" not in render_node(unconfigured, "old.application")
    assert "definition-ref" in render_node(configured, "old.application")


@pytest.mark.parametrize("entries, message", [
    ([{"node": "missing", "terms": ["term"]}], "definition"),
    ([{"node": "old.application", "terms": ["term"]}], "definition"),
    ([{"node": "old.bar", "terms": ["term"], "topics": ["missing"]}], "topic"),
    ([{"node": "old.bar", "terms": [""]}], "alias"),
    ([{"node": "old.bar", "terms": "term"}], "terms"),
    ([{"node": "old.bar", "terms": ["term"]},
      {"node": "old.quadratic", "terms": ["TERM"]}], "Ambiguous"),
])
def test_invalid_registry_is_diagnosed_before_publishing(kb, tmp_path, entries, message):
    (kb / "concept-links.yml").write_text(yaml.safe_dump({"concepts": entries}))
    diagnostics = check_knowledge_base(kb)
    assert any(d.level == "error" and message.lower() in d.message.lower() for d in diagnostics)
    site = tmp_path / "site"
    site.mkdir()
    sentinel = site / "preserve.txt"
    sentinel.write_text("previous build")
    with pytest.raises(ValueError, match=f"(?i){message}"):
        publish(kb, site)
    assert sentinel.read_text() == "previous build"


def test_html_protection_longest_match_and_idempotence():
    from tools.knowledge.definition_links import link_definitions
    from tools.knowledge.renderer import TEX_MATH_RE
    aliases = {"cover": ("a", "a.html", "Cover"),
               "minimal cover": ("b", "b.html", "Minimal cover")}
    protected = r'<h2>cover</h2><code>cover</code><a href="old">cover</a>\(\text{cover}\)[[node:a|cover]]'
    assert link_definitions(protected, aliases, TEX_MATH_RE) == protected
    linked = link_definitions("Minimal\ncover, uncovered", aliases, TEX_MATH_RE)
    assert linked.count("<a ") == 1 and 'href="b.html"' in linked
    assert link_definitions(linked, aliases, TEX_MATH_RE) == linked


def test_rebasing_does_not_edit_code_or_external_urls():
    from tools.knowledge.definition_links import rebase_payload_links
    html = '<code>&lt;a href="example.html"&gt;</code><a href="../definitions/a.html#x">a</a><a href="https://example.org/a">external</a>'
    linked = rebase_payload_links(html, "book.chapter")
    assert '<code>&lt;a href="example.html"&gt;</code>' in linked
    assert 'href="book/definitions/a.html#x"' in linked
    assert 'href="https://example.org/a"' in linked
