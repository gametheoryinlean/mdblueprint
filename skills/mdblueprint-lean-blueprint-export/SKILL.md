---
name: mdblueprint-lean-blueprint-export
description: Use when turning staged node drafts into a generated mdblueprint bundle with mdblueprint.yml and node files.
---

# mdblueprint-lean-blueprint-export

Materialize a downstream mdblueprint bundle from staged node drafts.

## Inputs

- staged node drafts
- theorem dependency evidence
- optional topic hints

## Output

- `mdblueprint.yml`
- generated node tree
- downstream bundle metadata
- review artifacts for graph and dependency changes

## Rules

- Keep the add-on downstream from source-text extraction.
- Do not overwrite upstream authored files unless the orchestrator explicitly asks for an apply step.
- Do not use regex or natural-language parsing for this materialization step.
- Keep blueprint generation separate from theorem extraction and node drafting.
- Produce a generated tree that can be compared against the core mdblueprint baseline.
