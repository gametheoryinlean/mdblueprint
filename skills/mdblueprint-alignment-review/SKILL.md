---
name: mdblueprint-alignment-review
description: Use when checking whether Lean declarations semantically match mdblueprint Markdown nodes.
---

# mdblueprint-alignment-review

Check whether a Lean declaration semantically matches a Markdown node.

## When to use

When verifying that a Lean formalization correctly represents the mathematical content of a knowledge node.

## Workflow

1. Run Python mechanical prechecks: module existence, declaration existence, sorry/admit status.
2. Package the Markdown statement, Lean signature, dependencies, and source snippets.
3. Invoke the semantic alignment verifier (LLM).
4. Write an alignment report under `docs/knowledge/reviews/`.

## Decision vocabulary

- `aligned` — the Lean declaration matches the Markdown statement
- `lean_stronger` — Lean proves more than Markdown claims
- `lean_weaker` — Lean proves less
- `lean_special_case` — Lean handles a special case only
- `lean_extra_hypotheses` — Lean adds hypotheses not in Markdown
- `lean_missing_hypotheses` — Lean omits hypotheses from Markdown
- `definition_mismatch` — definitions differ semantically
- `uncertain` — cannot determine

## Report format

See `references/alignment-report-schema.md`.
