---
name: mdblueprint-lean-node-generation
description: Use when turning theorem-name records and theorem dependencies into staged Markdown node drafts for the add-on.
---

# mdblueprint-lean-node-generation

Generate staged Markdown node drafts from theorem-name records and theorem dependencies.

## Inputs

- theorem-name records
- theorem dependency edges
- project metadata

## Output

- staged Markdown node drafts
- per-node frontmatter
- `uses` proposals derived from theorem dependencies
- review-friendly evidence fields

## Rules

- Draft nodes only.
- Do not commit the drafts into the authored baseline.
- Do not generate final blueprint metadata here.
- Preserve source theorem names and modules in frontmatter.
- Keep the output structured for downstream `mdblueprint` generation.

## Next stage

- pass the staged node drafts to `mdblueprint-lean-blueprint-export`
