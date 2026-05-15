import textwrap
from pathlib import Path

import markdown

from tools.knowledge.publish import _convert_markdown_preserving_tex, publish


def _render(source: str) -> str:
    md = markdown.Markdown(extensions=["tables"])
    return _convert_markdown_preserving_tex(md, textwrap.dedent(source).strip())


def test_preserves_inline_math_with_subscripts_superscripts_and_emphasis_outside_math():
    html = _render(r"""
    This is *important* outside math, while $x_i^2$ and \(y_i^2\) stay intact.
    """)

    assert "<em>important</em>" in html
    assert "$x_i^2$" in html
    assert r"\(y_i^2\)" in html
    assert "<em>2</em>" not in html


def test_preserves_display_math_blocks_and_multiline_environments():
    html = _render(r"""
    \[
    \begin{aligned}
    x_i^2 &= y_i^2 \\
    z_i &= x_i + y_i
    \end{aligned}
    \]

    $$
    \begin{cases}
    x & x \ge 0 \\
    -x & x < 0
    \end{cases}
    $$

    \[
    \begin{matrix}
    1 & 0 \\
    0 & 1
    \end{matrix}
    \]
    """)

    assert r"\begin{aligned}" in html
    assert r"\end{cases}" in html
    assert r"\begin{matrix}" in html
    assert "<em>" not in html


def test_escaped_dollars_and_markdown_links_survive_conversion():
    html = _render(r"""
    The literal price is \$5, and [a reference](https://example.test) follows.
    The formula is $p_i \le q_i$.
    """)

    assert r"\$5" in html
    assert '<a href="https://example.test">a reference</a>' in html
    assert r"$p_i \le q_i$" in html


def test_preserves_simple_inline_math_inside_markdown_tables():
    html = _render(r"""
    | object | expression |
    | --- | --- |
    | vector | $x_i^2$ |
    | tuple | \((x_i, y_i)\) |
    """)

    assert "<table>" in html
    assert "$x_i^2$" in html
    assert r"\((x_i, y_i)\)" in html


def test_publish_preserves_math_in_statement_proof_and_graph_modal(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    node_dir = knowledge_root / "nodes" / "analysis"
    node_dir.mkdir(parents=True)
    (node_dir / "estimate.md").write_text(
        textwrap.dedent(
            r"""
            ---
            id: analysis.estimate
            title: Estimate
            kind: theorem
            status: admitted
            uses: []
            tags:
              - analysis
            verification:
              statement: accepted
              proof: accepted
            ---

            # Estimate

            If $x_i^2 \le y_i^2$, then the estimate is bounded.

            \[
            x_i^2 \le y_i^2
            \]

            *Proof.*
            Use \(x_i \le y_i\) and the table:

            | step | bound |
            | --- | --- |
            | one | $x_i^2$ |
            """
        ).strip(),
        encoding="utf-8",
    )

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "analysis" / "analysis_estimate.html").read_text(encoding="utf-8")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text(encoding="utf-8")

    assert "$x_i^2 \\le y_i^2$" in node_page
    assert "\\[\nx_i^2 \\le y_i^2\n\\]" in node_page
    assert r"\(x_i \le y_i\)" in node_page
    assert "$x_i^2$" in node_page
    assert '<details class="proof-details">' in node_page
    assert "$x_i^2 \\le y_i^2$" in graph_page
