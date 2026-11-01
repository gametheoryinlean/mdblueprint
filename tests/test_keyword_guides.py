"""Authored keyword guides share mathematical references with node pages."""
from pathlib import Path

import pytest
import yaml

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.publish import publish
from tools.knowledge.renderer import render_keyword


def _write_node(root: Path, node_id: str, topic: str, kind: str, body: str):
    directory = root / "nodes" / topic
    directory.mkdir(parents=True, exist_ok=True)
    metadata = dict(
        id=node_id, title=node_id, kind=kind, status="admitted",
        primary_topic=topic, tags=["roots"],
    )
    (directory / f"{node_id}.md").write_text(
        "---\n" + yaml.safe_dump(metadata) + "---\n" + body,
        encoding="utf-8",
    )


@pytest.fixture
def kb(tmp_path):
    root = tmp_path / "knowledge"
    _write_node(root, "old.alpha", "book.definitions", "definition", "A root lattice.")
    _write_node(root, "old.result", "book.chapter", "theorem", "A consequence.")
    (root / "concept-links.yml").write_text(yaml.safe_dump({"concepts": [
        {"node": "old.alpha", "terms": ["root lattice"], "topics": ["book.chapter"]},
        {"node": "old.alpha", "terms": ["global datum"]},
    ]}), encoding="utf-8")
    (root / "keywords").mkdir()
    return root


def test_keyword_guide_preserves_math_resolves_refs_and_scoped_definitions(kb, tmp_path):
    (kb / "keywords/roots.md").write_text(
        "---\ntitle: Root definitions and consequences\nprimary_topic: book.chapter\n---\n"
        "## Definitions and proof route\n\n"
        "A root lattice leads to [[node:old.result|the consequence]].\n\n"
        r"\[\alpha \le \beta\]" + "\n",
        encoding="utf-8",
    )
    ctx = KnowledgeContext.load(kb)
    html = render_keyword(ctx, "roots")
    assert "<h1>Root definitions and consequences</h1>" in html
    assert 'class="keyword-introduction"' in html
    assert html.index("Definitions and proof route") < html.index("blueprint-node-list")
    assert 'href="../book/chapter/old_result.html"' in html
    assert 'href="../book/definitions/old_alpha.html"' in html
    assert 'class="node-ref definition-ref"' in html
    assert r"\alpha \le \beta" in html
    assert "[[node:" not in html
    assert "primary_topic:" not in html
    assert all(not node.uses for node in ctx.all_nodes)

    site = tmp_path / "site"
    publish(kb, site)
    assert (site / "keywords/roots.html").read_text(encoding="utf-8") == html


def test_plain_keyword_guide_uses_global_aliases_without_guessing_scope(kb):
    (kb / "keywords/roots.md").write_text(
        "A global datum. A root lattice.\n", encoding="utf-8"
    )
    html = render_keyword(KnowledgeContext.load(kb), "roots")
    assert "Keyword: roots" in html
    assert 'href="../book/definitions/old_alpha.html"' in html
    assert html.count('class="node-ref definition-ref"') == 1
    assert "A root lattice." in html


def test_missing_guide_keeps_keyword_node_listing(kb):
    html = render_keyword(KnowledgeContext.load(kb), "roots")
    assert "<h1>Keyword: roots</h1>" in html
    assert "keyword-introduction" not in html
    assert "blueprint-node-list" in html
    assert "old.result" in html


@pytest.mark.parametrize("metadata", [
    "primary_topic: book.missing",
    "primary_topic: [book.chapter]",
    "title: 7",
])
def test_invalid_guide_metadata_is_rejected(kb, metadata):
    (kb / "keywords/roots.md").write_text(
        f"---\n{metadata}\n---\nThe proof route.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="keyword guide"):
        render_keyword(KnowledgeContext.load(kb), "roots")


def test_unresolved_guide_reference_preserves_existing_published_site(kb, tmp_path):
    (kb / "keywords/roots.md").write_text("[[node:missing.node]]\n", encoding="utf-8")
    site = tmp_path / "site"
    site.mkdir()
    sentinel = site / "keep.txt"
    sentinel.write_text("previous build", encoding="utf-8")
    with pytest.raises(ValueError, match="keyword guide"):
        publish(kb, site)
    assert sentinel.read_text(encoding="utf-8") == "previous build"


def test_keyword_path_cannot_read_a_guide_outside_its_directory(kb):
    node = kb / "nodes/book.chapter/old.result.md"
    node.write_text(node.read_text().replace("- roots", "- ../outside"), encoding="utf-8")
    (kb / "outside.md").write_text("Outside content", encoding="utf-8")
    with pytest.raises(ValueError, match="keyword guide"):
        render_keyword(KnowledgeContext.load(kb), "../outside")


def test_malformed_frontmatter_has_keyword_context(kb):
    (kb / "keywords/roots.md").write_text(
        "---\ntitle: [unterminated\n---\nGuide.\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="keyword guide"):
        render_keyword(KnowledgeContext.load(kb), "roots")


def test_keyword_definition_links_preserve_code_math_and_existing_links(kb):
    (kb / "keywords/roots.md").write_text(
        "A global datum. " + chr(96) + "global datum" + chr(96) + ". "
        + r"\(\text{global datum}\)" + ". [global datum](https://example.org).\n",
        encoding="utf-8",
    )
    html = render_keyword(KnowledgeContext.load(kb), "roots")
    assert html.count('class="node-ref definition-ref"') == 1
    assert "<code>global datum</code>" in html
    assert r"\text{global datum}" in html
    assert 'href="https://example.org">global datum</a>' in html
