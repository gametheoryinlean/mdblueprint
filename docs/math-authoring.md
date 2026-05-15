# Math Authoring and Render Checks

Markdown node bodies may contain TeX math. The source remains Markdown, and the
published site renders math with KaTeX auto-render in the browser.

## Delimiters

Default supported delimiters:

| Purpose | Preferred | Also enabled |
| --- | --- | --- |
| Inline math | `\(...\)` | `$...$` |
| Display math | `\[...\]` | `$$...$$` |

Use the preferred delimiters for new nodes:

```markdown
A morphism \(f : X \to Y\) is an isomorphism if there is a morphism
\(g : Y \to X\) such that \(g \circ f = \operatorname{id}_X\) and
\(f \circ g = \operatorname{id}_Y\).

\[
\begin{aligned}
g \circ f &= \operatorname{id}_X, \\
f \circ g &= \operatorname{id}_Y.
\end{aligned}
\]
```

Use `\$` for a literal dollar sign. Avoid mixing `$...$` with prose that contains
unescaped dollar signs.

`math.delimiters` in project config controls the delimiter list passed to KaTeX
auto-render. Markdown preservation and static preflight diagnostics are designed for
the default delimiter family shown above. Do not introduce new delimiter syntaxes
unless you also verify the published HTML carefully with the browser render checker.

## Display Environments

Wrap display environments in display delimiters. Do not write a bare environment in
Markdown:

```markdown
\[
\begin{cases}
x, & x \ge 0, \\
-x, & x < 0.
\end{cases}
\]
```

Common KaTeX-compatible environments such as `aligned`, `cases`, `matrix`,
`pmatrix`, and `bmatrix` are expected to work when wrapped in display delimiters.
The static checker verifies delimiter and `\begin`/`\end` balance, but it does not
prove that every environment is supported by KaTeX. The browser render check is the
final rendering authority.

## Project Macros

Declare reusable macros once in `docs/knowledge/mdblueprint.yml`:

```yaml
site:
  title: Algebra Blueprint

math:
  macros:
    R: "\\mathbb{R}"
    Hom: "\\operatorname{Hom}"
  delimiters:
    inline:
      - ["\\(", "\\)"]
      - ["$", "$"]
    display:
      - ["\\[", "\\]"]
      - ["$$", "$$"]
  throw_on_error: false
```

Macro contract:

- Write macro keys without the leading slash: `R`, not `\R`.
- Use the macro in node bodies with the leading slash: `\R`.
- Do not put `\newcommand` or TeX preamble commands in node bodies.
- Static checks reject unknown letter macros unless they are built in or declared in
  `math.macros`.
- The publisher passes declared macros to KaTeX as browser auto-render options.

## Markdown Interaction

The publisher protects recognized math spans before Markdown conversion, then restores
them for KaTeX. This prevents Markdown emphasis from damaging common math such as
subscripts, products, and underscores inside recognized delimiters.

Authoring contract:

- Put all TeX math inside recognized inline or display delimiters.
- Keep prose Markdown outside math delimiters.
- Use Markdown tables only for simple inline math. Display math inside table cells
  is warned about because it often renders poorly.
- Do not rely on MathJax extensions. The generated site uses KaTeX, not MathJax.
- Do not use LaTeX theorem, proof, or document environments in the node body. The
  node `kind` and publisher provide theorem styling; proof folding comes from
  Markdown proof markers.

## Static Preflight Diagnostics

Run deterministic checks before publishing:

```bash
uv run python -m tools.knowledge.check docs/knowledge
```

The static math checker reports:

- unmatched `$`, `$$`, `\(`, `\)`, `\[`, or `\]` delimiters;
- unmatched or mismatched `\begin{...}` / `\end{...}` pairs;
- unknown letter macros not present in the built-in allowlist or `math.macros`;
- display math inside Markdown table cells.

Static diagnostics are syntax preflight checks. They do not execute a browser, load
KaTeX assets, or prove that every formula will render beautifully.

## Browser Render Verification

After publishing, run the browser render checker:

```bash
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
uv run --extra browser python -m tools.knowledge.render_check /tmp/mdblueprint-site
```

Before the first browser run, install Chromium for Playwright:

```bash
uv run --extra browser playwright install chromium
```

To check one page:

```bash
uv run --extra browser python -m tools.knowledge.render_check /tmp/mdblueprint-site --page algebra/algebra_group.html
```

The render checker serves the published site locally, opens HTML pages in Chromium,
reveals graph modals, and reports:

- failed KaTeX asset requests;
- relevant browser console errors;
- `.katex-error` elements;
- source pages that contain math but produce no rendered `.katex` elements;
- raw TeX delimiters still visible after rendering.

Browser render verification is the release QA check. A clean static check is necessary
but not sufficient before publishing a site for readers.

## Common Diagnostics

`unmatched math delimiter`

: Close the delimiter, change to the preferred `\(...\)` or `\[...\]` form, or escape
  a literal dollar as `\$`.

`unknown macro \Foo; declare it in math.macros`

: Fix the macro spelling or add `Foo` to `math.macros` in the project config.

`display math inside a Markdown table cell may render poorly`

: Move the display formula outside the table, or rewrite the cell with inline math.

`source contains math but no rendered .katex elements were found`

: KaTeX did not render on that page. Check asset loading, delimiter configuration,
  and browser console errors.

`raw TeX delimiter remains after browser rendering`

: A formula was not recognized or failed to render. Check delimiter balance and
  whether the formula is inside an HTML area hidden from auto-render.

`KaTeX error elements present`

: The browser parsed the math but KaTeX rejected the expression. Reduce the formula
  to a smaller example, check KaTeX support, and move reusable notation into
  `math.macros` when appropriate.
