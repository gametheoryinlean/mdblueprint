---
name: mdblueprint-node-author
description: Use when creating or editing Markdown knowledge nodes for an mdblueprint knowledge base.
---

# mdblueprint-node-author

Create or edit Markdown knowledge nodes by hand.

## When to use

When authoring mathematical content for the knowledge base.

## Checklist

- [ ] Read `docs/knowledge/mdblueprint.yml` first; if `topics` is configured, use canonical topic ids from the registry, not aliases.
- [ ] Read the nearest folder-level `topics.md` catalog before choosing topic names.
- [ ] Math-only body — no operational sections (status, implementation notes, etc.)
- [ ] Structured YAML metadata following node-format.md
- [ ] TeX uses supported delimiters and project macros from math-authoring.md
- [ ] Stable node id; do not change it just to alter graph topic membership
- [ ] One `primary_topic` home topic and a `topics` list containing every graph view that should include the node
- [ ] One concept, definition, theorem, example, or proof-plan per file
- [ ] Correct verification fields for the node kind (statement for theorems, definition for definitions)
- [ ] Source spans with artifact binding if content comes from a reference
- [ ] Incomplete statements marked with review status, not hidden

## Must not

- Must not set `status: admitted` without review evidence — use `staged` for new content.
- Must not write operational content (implementation notes, status tracking, TODOs) in the Markdown body.
- Must not invent dependencies beyond what can be justified from the source or existing nodes.
- Must not invent a topic not in the canonical registry or nearest `topics.md`; if no topic fits, propose one in a request instead of silently inventing a name.

## Must read

- `docs/node-format.md`
- `docs/topic-model.md`
- `docs/math-authoring.md`
- `references/node-template.md`
- `docs/knowledge/mdblueprint.yml` (topic registry)
- nearest `topics.md` catalog when present
