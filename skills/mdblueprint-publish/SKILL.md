---
name: mdblueprint-publish
description: Use when generating, publishing, or checking the mdblueprint static site, dependency graph, graph.json, or blueprint-style pages.
---

# mdblueprint-publish

Generate or check the blueprint-like website and DAG.

## When to use

When building the static site or verifying the knowledge graph output.

## Workflow

1. Run `uv run python -m tools.knowledge.check docs/knowledge` — fix any errors.
2. Run `uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site` — generates site.
3. Confirm the generated index and node pages use the project title and short title from `docs/knowledge/mdblueprint.yml`, or the configured `--config` path.
4. If `lean.repositories` is configured, confirm Lean declaration modals on node pages and `dep_graph_document.html` contain source links rather than `Unresolved` markers.
5. Run `uv run --extra browser python -m tools.knowledge.render_check /tmp/mdblueprint-site` for strict browser math verification when the browser runtime is installed.
6. Inspect the output under the chosen site directory for missing nodes, broken links, or graph errors.
7. Check every generated node page, not only the index:
   - Confirm each node id in `graph.json` has a corresponding HTML page.
   - Open or programmatically inspect each node page and `dep_graph_document.html`.
   - Scan for KaTeX render errors and browser console errors.
   - Scan rendered HTML for Markdown-emphasis damage inside TeX, especially `<em>` or `<strong>` tags between math delimiters.
   - For any node whose Markdown body contains TeX, verify that the page has no raw broken formula fragments such as unmatched `$`, inserted `<em>`, or visibly unrendered display math.
8. Report the number of node pages checked and list any pages with LaTeX/rendering or Lean-link issues.

## Rules

- Do not call an LLM to generate final HTML or graph data.
- Do not edit node content to make publishing pass.
- Do not infer missing dependencies.
- Do not publish after a spot check only; every generated node page must be checked for rendering regressions.
