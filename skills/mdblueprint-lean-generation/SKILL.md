---
name: mdblueprint-lean-generation
description: Use when generating Lean 4 declarations, proof skeletons, or patch proposals from admitted mdblueprint Markdown nodes.
---

# mdblueprint-lean-generation

Generate Lean 4 proposals from admitted Markdown nodes.

## When to use

When turning admitted knowledge nodes into Lean declarations or proof skeletons.

## Workflow

1. Read the admitted node and its dependencies.
2. Inspect the Lean declaration index and existing Lean modules.
3. Generate a Lean file or patch proposal.
4. If an auxiliary node is needed, write a request to `docs/knowledge/requests/` — never create an admitted node directly.
5. Justify every proposed new node according to the request schema.

## Rules

- Never add admitted Markdown nodes directly.
- Never generate final DAG edges.
- Must not weaken the mathematical statement without a review note explaining the discrepancy.
- Proposed auxiliary nodes must explain why existing nodes are insufficient.

## New-node request format

See `references/new-node-request-schema.md`.
