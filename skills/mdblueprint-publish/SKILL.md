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
4. Inspect the output under the chosen site directory for missing nodes, broken links, or graph errors.

## Rules

- Do not call an LLM to generate final HTML or graph data.
- Do not edit node content to make publishing pass.
- Do not infer missing dependencies.
