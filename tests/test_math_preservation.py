import json
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


def test_preserves_inline_math_wrapped_across_a_soft_line_break():
    html = _render(r"""
    The elliptic pairing on class functions: $(f, g)_{\mathrm{ell}} =
    |W|^{-1}\sum_{w \text{ ell}} f(w)g(w^{-1})$.
    """)

    assert r"_{\mathrm{ell}}" in html
    assert r"\sum_{w \text{ ell}}" in html
    assert "<em>" not in html


def test_inline_math_does_not_span_a_paragraph_break():
    html = _render(r"""
    A stray dollar $5 sits here.

    Another stray dollar $7 sits in the next paragraph.
    """)

    # The two lone `$` are in separate paragraphs and must not be paired into
    # one bogus math span that swallows the intervening text.
    assert "<p>" in html
    assert html.count("<p>") == 2


def test_list_directly_after_a_paragraph_line_renders_as_a_list():
    html = _render(r"""
    Elliptic elements play a key role in:
    - The elliptic representation theory of $p$-adic groups.
    - The elliptic pairing on class functions.
    """)

    assert "<ul>" in html
    assert html.count("<li>") == 2
    assert "$p$" in html


def test_ordered_list_directly_after_a_paragraph_line_renders_as_a_list():
    html = _render(r"""
    The construction proceeds in two steps:
    1. Choose a maximal torus.
    2. Take its centralizer.
    """)

    assert "<ol>" in html
    assert html.count("<li>") == 2


def test_numbered_prose_line_does_not_interrupt_a_paragraph():
    html = _render(r"""
    The theorem was first proved in
    1965. It was later refined.
    """)

    # CommonMark: an ordered list may interrupt a paragraph only when it
    # starts at 1, so a stray year like "1965." stays prose.
    assert "<ol>" not in html


def test_bold_lead_in_before_a_list_renders_as_a_list():
    html = _render(r"""
    **Examples.**
    - \(\operatorname{SL}_n\) inside \(\operatorname{GL}_n\).
    - The additive group.
    """)

    assert "<ul>" in html
    assert html.count("<li>") == 2


def test_list_inside_fenced_code_block_is_left_alone():
    html = _render("""
    Example input:

    ```
    header line
    - not a real list
    ```
    """)

    assert "<ul>" not in html


def test_setext_heading_underline_is_not_treated_as_a_list():
    html = _render("""
    Section title
    -------------

    Body text.
    """)

    assert "<ul>" not in html
    assert "<h2>" in html


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
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "analysis_estimate.json").read_text(encoding="utf-8")
    )

    assert "$x_i^2 \\le y_i^2$" in node_page
    assert "\\[\nx_i^2 \\le y_i^2\n\\]" in node_page
    assert r"\(x_i \le y_i\)" in node_page
    assert "$x_i^2$" in node_page
    assert '<details class="proof-details">' in node_page
    assert "$x_i^2 \\le y_i^2$" in graph_payload["body_html"]
    assert r"\(x_i \le y_i\)" in graph_payload["proof_html"]
