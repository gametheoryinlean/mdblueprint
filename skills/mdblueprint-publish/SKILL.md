# mdblueprint-publish

Generate or check the blueprint-like website and DAG.

## When to use

When building the static site or verifying the knowledge graph output.

## Workflow

1. Run `python -m tools.knowledge.check docs/knowledge` — fix any errors.
2. Run `python -m tools.knowledge.publish docs/knowledge` — generates site.
3. Inspect the output under `docs/knowledge/site/` for missing nodes, broken links, or graph errors.

## Rules

- Do not call an LLM to generate final HTML or graph data.
- Do not edit node content to make publishing pass.
- Do not infer missing dependencies.
