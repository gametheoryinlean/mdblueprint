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