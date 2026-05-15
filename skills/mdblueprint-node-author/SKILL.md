---
name: mdblueprint-node-author
description: Use when creating or editing Markdown knowledge nodes for an mdblueprint knowledge base.
---

# mdblueprint-node-author

Create or edit Markdown knowledge nodes by hand.

## When to use

When authoring mathematical content for the knowledge base.

## Checklist

- [ ] Math-only body — no operational sections (status, implementation notes, etc.)
- [ ] Structured YAML metadata following node-format.md
- [ ] Stable topic-scoped id
- [ ] One concept, definition, theorem, example, or proof-plan per file
- [ ] Correct verification fields for the node kind (statement for theorems, definition for definitions)
- [ ] Source spans with artifact binding if content comes from a reference
- [ ] Incomplete statements marked with review status, not hidden

## Must not

- Must not set `status: admitted` without review evidence — use `staged` for new content.
- Must not write operational content (implementation notes, status tracking, TODOs) in the Markdown body.
- Must not invent dependencies beyond what can be justified from the source or existing nodes.

## Must read

- `docs/node-format.md`
- `references/node-template.md`
