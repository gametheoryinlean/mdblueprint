---
name: mdblueprint-alignment-review
description: Use when checking whether Lean declarations semantically match mdblueprint Markdown nodes.
---

# mdblueprint-alignment-review

Check whether one candidate Lean declaration semantically matches one Markdown
node from a bounded Python-generated bundle.

## When to use

When verifying that a Lean formalization correctly represents the mathematical
content of a knowledge node. Use the bundle from `tools.knowledge.lean_alignment`;
the verifier must not scan the repository or invent extra Lean context.

## Workflow

1. Read only the bounded bundle supplied by Python.
2. Compare the Markdown statement/body with the Lean signature/snippet.
3. Return exactly one structured classification and evidence list.
4. Let Python validate and write the report under `docs/knowledge/reviews/`.

The agent must not write `verification.alignment` or node status directly.

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
