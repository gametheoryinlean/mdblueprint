from pathlib import Path

import pytest

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.renderer import (
    _short_revision, node_detail_payload, render_graph_page, render_index,
    render_keyword, render_node, render_topic,
)

KNOWLEDGE_ROOT = Path(__file__).parent.parent / "docs" / "knowledge"


@pytest.fixture(scope="module")
def ctx():
    return KnowledgeContext.load(KNOWLEDGE_ROOT)


@pytest.fixture(scope="module")
def ctx_dev():
    return KnowledgeContext.load(KNOWLEDGE_ROOT, dev_mode=True)


class TestRenderHappy:
    def test_index_contains_topics(self, ctx):
        html = render_index(ctx)
        assert "Strategic Game" in html

    def test_node_includes_body_and_deps(self, ctx):
        html = render_node(ctx, "strategic_games.nash_equilibrium")
        assert "best_response" in html

    def test_topic_returns_html(self, ctx):
        html = render_topic(ctx, "strategic_games")
        assert "<html" in html.lower() or "<!DOCTYPE" in html

    def test_node_detail_payload_shape(self, ctx):
        p = node_detail_payload(ctx, "strategic_games.nash_equilibrium")
        assert p["id"] == "strategic_games.nash_equilibrium"
        assert "body_html" in p
        assert isinstance(p["deps"], list)
        assert isinstance(p["dependents"], list)


class TestDevModeFlag:
    def test_dev_mode_off_no_sse(self, ctx):
        html = render_index(ctx)
        assert "EventSource('/_dev/events')" not in html

    def test_dev_mode_on_includes_sse(self, ctx_dev):
        html = render_index(ctx_dev)
        assert "EventSource('/_dev/events')" in html


class TestAutolinkBareNodeRefs:
    """Issue #134: <code>known.node.id</code> spans should auto-link."""

    def test_known_id_autolinks(self):
        from tools.knowledge.models import Node
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        nodes = {
            "topic.foo": Node(id="topic.foo", title="Foo", kind="definition", status="admitted"),
        }
        html = "<p>See <code>topic.foo</code> for details.</p>"
        result = _autolink_bare_node_refs_in_html(html, nodes)
        assert 'href=' in result
        assert 'class="node-ref"' in result
        assert 'data-node-id="topic.foo"' in result
        assert "<code>topic.foo</code>" in result  # the <code> styling stays

    def test_unknown_id_is_left_alone(self):
        from tools.knowledge.models import Node
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        nodes = {
            "topic.foo": Node(id="topic.foo", title="Foo", kind="definition", status="admitted"),
        }
        html = "<p>See <code>topic.bar</code> for details.</p>"
        result = _autolink_bare_node_refs_in_html(html, nodes)
        # Unknown id stays as bare <code>; no anchor wrapper.
        assert result == html

    def test_pre_block_content_is_not_autolinked(self):
        from tools.knowledge.models import Node
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        nodes = {
            "topic.foo": Node(id="topic.foo", title="Foo", kind="definition", status="admitted"),
        }
        html = "<pre><code>topic.foo</code></pre>"
        result = _autolink_bare_node_refs_in_html(html, nodes)
        # The fenced code block stays untouched — no anchor wrapper.
        assert result == html

    def test_already_anchored_content_is_not_double_wrapped(self):
        from tools.knowledge.models import Node
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        nodes = {
            "topic.foo": Node(id="topic.foo", title="Foo", kind="definition", status="admitted"),
        }
        html = '<p>See <a class="node-ref" href="topic/foo.html"><code>topic.foo</code></a></p>'
        result = _autolink_bare_node_refs_in_html(html, nodes)
        # The existing anchor stays exactly as is.
        assert result == html

    def test_single_segment_id_does_not_autolink(self):
        # The id pattern requires at least one dot, so bare `wsum` stays plain.
        from tools.knowledge.models import Node
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        nodes = {
            "wsum": Node(id="wsum", title="WSum", kind="definition", status="admitted"),
        }
        html = "<p>The <code>wsum</code> operator.</p>"
        result = _autolink_bare_node_refs_in_html(html, nodes)
        # No dot ⇒ not eligible for autolinking; stays as bare <code>.
        assert result == html

    def test_no_nodes_short_circuits(self):
        from tools.knowledge.renderer import _autolink_bare_node_refs_in_html

        html = "<p>See <code>topic.foo</code> here.</p>"
        assert _autolink_bare_node_refs_in_html(html, {}) == html


class TestAutolinkLeanDecls:
    """Inline `<code>decl_name</code>` should link to the GitHub source URL
    when the name matches an entry in the current node's lean.declarations
    (short or fully-qualified)."""

    def _refs(self):
        return [
            {
                "name": "Online.Auction.SingleItemAuction.welfare_can_be_zero",
                "qualified_name": "Online.Auction.SingleItemAuction.welfare_can_be_zero",
                "source_url": "https://github.com/org/repo/blob/abc/SIA.lean#L278",
            },
            {
                "name": "Online.Auction.SingleItemAuction.no_constant_competitive_ratio",
                "qualified_name": "Online.Auction.SingleItemAuction.no_constant_competitive_ratio",
                "source_url": "https://github.com/org/repo/blob/abc/SIA.lean#L320",
            },
        ]

    def test_short_name_links(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        decl_map = _build_lean_decl_url_map(self._refs())
        html = "<p><code>welfare_can_be_zero</code></p>"
        result = _autolink_lean_decls_in_html(html, decl_map)
        assert 'class="lean-decl-ref"' in result
        assert 'href="https://github.com/org/repo/blob/abc/SIA.lean#L278"' in result
        assert "<code>welfare_can_be_zero</code>" in result

    def test_fully_qualified_name_links(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        decl_map = _build_lean_decl_url_map(self._refs())
        html = "<p><code>Online.Auction.SingleItemAuction.welfare_can_be_zero</code></p>"
        result = _autolink_lean_decls_in_html(html, decl_map)
        assert 'href="https://github.com/org/repo/blob/abc/SIA.lean#L278"' in result

    def test_unknown_name_untouched(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        decl_map = _build_lean_decl_url_map(self._refs())
        html = "<p><code>something_else</code></p>"
        assert _autolink_lean_decls_in_html(html, decl_map) == html

    def test_pre_block_skipped(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        decl_map = _build_lean_decl_url_map(self._refs())
        html = "<pre><code>welfare_can_be_zero</code></pre>"
        assert _autolink_lean_decls_in_html(html, decl_map) == html

    def test_already_anchored_untouched(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        decl_map = _build_lean_decl_url_map(self._refs())
        html = '<p><a href="x"><code>welfare_can_be_zero</code></a></p>'
        assert _autolink_lean_decls_in_html(html, decl_map) == html

    def test_ambiguous_short_name_dropped(self):
        from tools.knowledge.renderer import (
            _autolink_lean_decls_in_html, _build_lean_decl_url_map,
        )
        refs = [
            {"name": "Foo.welfare", "qualified_name": "Foo.welfare",
             "source_url": "https://x/foo.lean#L1"},
            {"name": "Bar.welfare", "qualified_name": "Bar.welfare",
             "source_url": "https://x/bar.lean#L2"},
        ]
        decl_map = _build_lean_decl_url_map(refs)
        # Both fully-qualified names still resolve.
        assert decl_map["Foo.welfare"] == "https://x/foo.lean#L1"
        assert decl_map["Bar.welfare"] == "https://x/bar.lean#L2"
        # Bare `welfare` is ambiguous → not in the map.
        assert "welfare" not in decl_map
        # Inline mention stays plain.
        html = "<p>see <code>welfare</code></p>"
        assert _autolink_lean_decls_in_html(html, decl_map) == html

    def test_refs_without_source_url_skipped(self):
        from tools.knowledge.renderer import _build_lean_decl_url_map
        refs = [
            {"name": "Foo.bar", "qualified_name": None, "source_url": None},
        ]
        assert _build_lean_decl_url_map(refs) == {}

    def test_empty_map_short_circuits(self):
        from tools.knowledge.renderer import _autolink_lean_decls_in_html
        html = "<p><code>foo</code></p>"
        assert _autolink_lean_decls_in_html(html, {}) == html


class TestAutolinkLeanDeclsFallback:
    """Inline `<code>X</code>` should link via the project-wide Lean index
    when X is not in the node's YAML lean.declarations but resolves
    uniquely against the project index."""

    def test_unique_short_name_resolves_via_fallback(self):
        from tools.knowledge.renderer import _autolink_lean_decls_in_html

        def fallback(name):
            if name == "welfareAux_all_zero":
                return "https://x/sia.lean#L257"
            return None

        html = "<p>via <code>welfareAux_all_zero</code></p>"
        result = _autolink_lean_decls_in_html(html, {}, fallback=fallback)
        assert 'href="https://x/sia.lean#L257"' in result
        assert 'class="lean-decl-ref"' in result

    def test_explicit_map_wins_over_fallback(self):
        from tools.knowledge.renderer import _autolink_lean_decls_in_html

        def fallback(name):
            return "https://wrong/fallback.lean#L1"

        decl_to_url = {"foo": "https://right/explicit.lean#L42"}
        html = "<p><code>foo</code></p>"
        result = _autolink_lean_decls_in_html(html, decl_to_url, fallback=fallback)
        assert 'href="https://right/explicit.lean#L42"' in result
        assert "fallback.lean" not in result

    def test_fallback_returns_none_leaves_plain_code(self):
        from tools.knowledge.renderer import _autolink_lean_decls_in_html

        def fallback(name):
            return None

        html = "<p><code>unknown</code></p>"
        result = _autolink_lean_decls_in_html(html, {}, fallback=fallback)
        assert result == html


class TestLeanIndexResolveInline:
    """LeanIndex.resolve_inline handles fully-qualified, short, and
    ambiguous names."""

    def _make_index(self):
        from pathlib import Path
        from tools.knowledge.lean_index import LeanDeclaration, LeanIndex

        idx = LeanIndex()
        for q in [
            "Online.Auction.SingleItemAuction.welfareAux_all_zero",
            "Online.Auction.SingleItemAuction.welfare_can_be_zero",
            "Foo.bar.duplicated_name",
            "Foo.baz.duplicated_name",
        ]:
            short = q.rsplit(".", 1)[-1]
            idx.declarations[q] = LeanDeclaration(
                name=short, qualified_name=q, kind="theorem",
                file=Path("x.lean"), line=1,
                source_url=f"https://example.test/{q}",
            )
        return idx

    def test_fully_qualified_match(self):
        idx = self._make_index()
        d = idx.resolve_inline("Online.Auction.SingleItemAuction.welfare_can_be_zero")
        assert d is not None
        assert d.qualified_name == "Online.Auction.SingleItemAuction.welfare_can_be_zero"

    def test_unique_short_match(self):
        idx = self._make_index()
        d = idx.resolve_inline("welfareAux_all_zero")
        assert d is not None
        assert d.qualified_name.endswith(".welfareAux_all_zero")

    def test_ambiguous_short_returns_none(self):
        idx = self._make_index()
        assert idx.resolve_inline("duplicated_name") is None

    def test_unknown_returns_none(self):
        idx = self._make_index()
        assert idx.resolve_inline("nope") is None

    def test_partial_suffix_match(self):
        idx = self._make_index()
        d = idx.resolve_inline("SingleItemAuction.welfare_can_be_zero")
        assert d is not None
        assert d.qualified_name == "Online.Auction.SingleItemAuction.welfare_can_be_zero"


class TestShortRevision:
    def test_full_sha_truncated(self):
        assert _short_revision("a" * 40) == "aaaaaaa"

    def test_short_sha_preserved(self):
        assert _short_revision("deadbeef") == "deadbee"

    def test_seven_hex_truncated(self):
        assert _short_revision("0123456") == "0123456"

    def test_branch_main_preserved(self):
        assert _short_revision("main") == "main"

    def test_branch_master_preserved(self):
        assert _short_revision("master") == "master"

    def test_branch_with_slash_preserved(self):
        assert _short_revision("release/v0.1") == "release/v0.1"

    def test_tag_preserved(self):
        assert _short_revision("v1.2.3-rc4") == "v1.2.3-rc4"

    def test_none_returns_none(self):
        assert _short_revision(None) is None


class TestBoundaryConditions:
    def test_render_node_unknown_raises(self, ctx):
        with pytest.raises(KeyError):
            render_node(ctx, "does.not.exist")

    def test_render_topic_unknown_raises(self, ctx):
        with pytest.raises(KeyError):
            render_topic(ctx, "nonexistent_topic")

    def test_render_keyword_unknown_raises(self, ctx):
        with pytest.raises(KeyError):
            render_keyword(ctx, "no_such_tag")

    def test_node_detail_payload_unknown_raises(self, ctx):
        with pytest.raises(KeyError):
            node_detail_payload(ctx, "does.not.exist")

    def test_node_with_fenced_code_block(self, tmp_path):
        """Regression: ```lean fenced code blocks must render as <pre><code>,
        not as running <p> text with the triple-backticks visible."""
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "fenced.md").write_text(
            "---\nid: fenced.node\ntitle: Fenced Code\nkind: definition\nstatus: admitted\n---\n"
            "Prose paragraph.\n\n"
            "```lean\n"
            "def foo (n : ℕ) : ℕ := n + 1\n"
            "```\n\n"
            "Trailing paragraph.\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        html = render_node(ctx, "fenced.node")
        # Fenced code block should be wrapped in <pre><code>.
        assert "<pre>" in html and "<code" in html, (
            "fenced ```lean block was not rendered as <pre><code>"
        )
        # Triple backticks must not leak into rendered text.
        assert "```" not in html, "raw triple-backticks leaked into rendered HTML"

    def test_node_with_empty_body(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "empty.md").write_text(
            "---\nid: empty.node\ntitle: Empty Node\nkind: concept\nstatus: admitted\n---\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        html = render_node(ctx, "empty.node")
        assert "Empty Node" in html

    def test_node_with_proof_only_no_statement(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "proofonly.md").write_text(
            "---\nid: proof.node\ntitle: Proof Only\nkind: lemma\nstatus: admitted\n---\n"
            "**Proof.** The proof goes here.\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        html = render_node(ctx, "proof.node")
        assert "Proof Only" in html

    def test_node_with_unresolved_ref(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "has_ref.md").write_text(
            "---\nid: ref.node\ntitle: Has Ref\nkind: concept\nstatus: admitted\n---\n"
            "See [[node:unknown_node]] for details.\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        html = render_node(ctx, "ref.node")
        assert "unresolved" in html or "unknown_node" in html

    def test_node_with_custom_label_ref(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "a.md").write_text(
            "---\nid: ref.custom\ntitle: Custom Label\nkind: concept\nstatus: admitted\n---\n"
            "Body.\n"
        )
        (nodes / "b.md").write_text(
            "---\nid: ref.consumer\ntitle: Consumer\nkind: concept\nstatus: admitted\n---\n"
            "See [[node:ref.custom|Custom Labeled Ref]] for details.\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        html = render_node(ctx, "ref.consumer")
        assert "Custom Labeled Ref" in html

    def test_node_with_no_uses_no_deps(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "solo.md").write_text(
            "---\nid: solo.node\ntitle: Solo Node\nkind: concept\nstatus: admitted\n---\n"
            "Lonely body.\n"
        )
        ctx = KnowledgeContext.load(tmp_path)
        p = node_detail_payload(ctx, "solo.node")
        assert p["deps"] == []
        assert p["dependents"] == []

    def test_node_with_lean_decls_lean_false(self, tmp_path):
        nodes = tmp_path / "nodes"
        nodes.mkdir(parents=True)
        (nodes / "lean_node.md").write_text(
            "---\nid: lean.node\ntitle: Lean Node\nkind: theorem\nstatus: admitted\nlean:\n  declarations:\n    - Some.Decl\n---\nStatement.\n"
        )
        ctx = KnowledgeContext.load(tmp_path, lean=False)
        p = node_detail_payload(ctx, "lean.node")
        assert p["lean_refs"][0]["status"] == "raw"

    def test_concurrent_render_node_succeeds(self, ctx):
        import threading
        errors = []
        def render():
            try:
                render_node(ctx, "strategic_games.nash_equilibrium")
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=render) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors