import json
import textwrap
from pathlib import Path

from tools.knowledge.publish import publish


def _write_math_fixture(knowledge_root: Path) -> None:
    node_dir = knowledge_root / "nodes" / "analysis"
    node_dir.mkdir(parents=True)
    (node_dir / "limit.md").write_text(
        textwrap.dedent(
            r"""
            ---
            id: analysis.limit_unique
            title: Limit Is Unique
            kind: theorem
            status: admitted
            uses: []
            tags:
              - analysis
            verification:
              statement: accepted
              proof: accepted
            ---

            # Limit Is Unique

            Inline math $\lim x_n = x$ should render.

            \[
            \lim_{n \to \infty} x_n = x
            \]

            *Proof.*
            If $x$ and $y$ are both limits, then
            $d(x,y) \le d(x,x_n) + d(x_n,y)$ for all large $n$.
            """
        ).strip(),
        encoding="utf-8",
    )


def test_iter_html_pages_includes_nodes_and_graph(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    _write_math_fixture(knowledge_root)
    site_dir = tmp_path / "site"
    publish(knowledge_root, site_dir)

    from tools.knowledge.render_check import iter_html_pages

    pages = {path.relative_to(site_dir).as_posix() for path in iter_html_pages(site_dir)}

    assert "index.html" in pages
    assert "dep_graph_document.html" in pages
    assert "analysis/analysis_limit_unique.html" in pages


def test_render_state_reports_katex_errors_from_browser():
    from tools.knowledge.render_check import PageRenderState, diagnose_render_state

    state = PageRenderState(
        path=Path("bad.html"),
        had_math_source=True,
        body_text="A malformed macro was rendered.",
        katex_count=1,
        katex_error_count=1,
        console_errors=[],
        failed_requests=[],
    )

    messages = diagnose_render_state(state)

    assert any("KaTeX error" in message for message in messages)


def test_render_state_reports_katex_error_expression_and_context():
    from tools.knowledge.render_check import KatexErrorDetail, PageRenderState, diagnose_render_state

    state = PageRenderState(
        path=Path("bad.html"),
        had_math_source=True,
        body_text="For every x outside C.",
        katex_count=1,
        katex_error_count=1,
        katex_errors=[
            KatexErrorDetail(
                expression=r"x\notin C",
                title="ParseError: Too many expansions",
                context="Suppose x\\notin C and choose a separator.",
            )
        ],
    )

    messages = diagnose_render_state(state)

    assert any(r"expression: x\notin C" in message for message in messages)
    assert any("ParseError: Too many expansions" in message for message in messages)
    assert any("context: Suppose x\\notin C" in message for message in messages)


def test_render_state_reports_raw_tex_residue_and_missing_katex():
    from tools.knowledge.render_check import PageRenderState, diagnose_render_state

    state = PageRenderState(
        path=Path("raw.html"),
        had_math_source=True,
        body_text=r"Raw delimiters remain: \(x_i\)",
        katex_count=0,
        katex_error_count=0,
        console_errors=[],
        failed_requests=[],
    )

    messages = diagnose_render_state(state)

    assert any("raw TeX delimiter" in message for message in messages)
    assert any("no rendered .katex" in message for message in messages)


def test_render_state_reports_katex_asset_failures():
    from tools.knowledge.render_check import PageRenderState, diagnose_render_state

    state = PageRenderState(
        path=Path("asset.html"),
        had_math_source=True,
        body_text="No residue.",
        katex_count=1,
        katex_error_count=0,
        console_errors=[],
        failed_requests=["https://cdn.jsdelivr.net/npm/katex@0.16.46/dist/katex.min.js"],
    )

    messages = diagnose_render_state(state)

    assert any("KaTeX asset failed" in message for message in messages)


def test_math_source_detection_ignores_renderer_configuration_scripts():
    from tools.knowledge.render_check import html_has_math_source

    html = r"""
    <script>
      renderMathInElement(document.body, {
        delimiters: [{ left: "$$", right: "$$", display: true }]
      });
    </script>
    <main>No mathematical source here.</main>
    """

    assert html_has_math_source(html) is False
    assert html_has_math_source(r"<main>Inline math \(x_i\).</main>") is True


def test_published_render_fixture_contains_math_on_node_and_graph_pages(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    _write_math_fixture(knowledge_root)
    site_dir = tmp_path / "site"
    publish(knowledge_root, site_dir)

    node_page = (site_dir / "analysis" / "analysis_limit_unique.html").read_text(encoding="utf-8")
    graph_payload = json.loads((site_dir / "node_payloads" / "analysis_limit_unique.json").read_text(encoding="utf-8"))
    graph_page = (site_dir / "dep_graph_document.html").read_text(encoding="utf-8")

    assert r"$\lim x_n = x$" in node_page
    assert r"\[" in node_page
    assert "proof-details" in node_page
    assert r"$d(x,y) \le d(x,x_n) + d(x_n,y)$" in graph_payload["proof_html"]
    assert "dep-modal-container" in graph_page
