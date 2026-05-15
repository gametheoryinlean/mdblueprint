---
name: mdblueprint-node-review
description: Use when reviewing staged mdblueprint nodes for mathematical fitness, generality, proof validity, or admission.
---

# mdblueprint-node-review

Review staged nodes for mathematical fitness before admission.

## When to use

When deciding whether a staged node should be admitted to the knowledge base.

## Workflow

1. Run deterministic Python checks: `python -m tools.knowledge.check`.
2. For definitions and concepts: invoke the statement/definition verifier.
3. For nodes with proof content: invoke the proof verifier.
4. Enforce the generality gate for required kinds (definition, lemma, proposition, theorem, external-theorem).
5. Produce review reports with explicit decisions under `docs/knowledge/reviews/`.
6. If all checks pass, recommend to the admission referee.

## Generality gate questions

For every subject kind, the reviewer must answer:

- What is the most general useful form of this statement?
- Is the current statement that form?
- If not, is the narrower form deliberately chosen?
- What assumptions might be removable?

## Report format

See `references/review-report-schema.md`.
