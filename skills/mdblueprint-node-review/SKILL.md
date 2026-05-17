---
name: mdblueprint-node-review
description: Use when reviewing staged mdblueprint nodes for mathematical fitness, generality, proof validity, or admission.
---

# mdblueprint-node-review

Review staged nodes for mathematical fitness before admission.

## When to use

When deciding whether a staged node should be admitted to the knowledge base.

## Workflow

1. Read `docs/knowledge/mdblueprint.yml` to know the canonical topic registry before reviewing any node.
2. Read any extraction reports under `docs/knowledge/reviews/` to find staged nodes created by source-extraction.
3. Run deterministic Python checks: `python -m tools.knowledge.check`.
4. For definitions and concepts: invoke the statement/definition verifier.
5. For nodes with proof content: invoke the proof verifier.
   - If the proof verifier returns `gap` for a small, local step, invoke the
     proof-fill skill (`skills/mdblueprint-proof-fill/SKILL.md`) as a bounded
     repair step. All three preconditions in that skill must hold before
     invoking it. Do not invoke proof-fill during statement review or for
     proofs that require a new reusable lemma.
   - If the proof verifier returns `critical`, stop and write a review report;
     do not attempt proof-fill.
6. Enforce the generality gate for required kinds (definition, lemma, proposition, theorem, external-theorem).
7. Check that each staged node's id prefix is a canonical topic id from the registry — flag any alias usage and note the canonical replacement in the report.
8. Produce review reports with explicit decisions under `docs/knowledge/reviews/`.
9. If all checks pass, recommend to the admission referee.
10. **Stop after writing the review report.** Do not automatically admit nodes; the referee makes that decision.

## Handoff contract

- Source extraction produces: staged nodes in `docs/knowledge/staged/` and an extraction report listing created paths.
- Node review consumes: staged nodes and the extraction report. Select nodes for review by listing `docs/knowledge/staged/` markdown files; optionally filter by paths in the extraction report.
- The review report is the durable handoff artifact for the admission referee. It is not consumed by any automated tool.

## Generality gate questions

For every subject kind, the reviewer must answer:

- What is the most general useful form of this statement?
- Is the current statement that form?
- If not, is the narrower form deliberately chosen?
- What assumptions might be removable?

## Report format

See `references/review-report-schema.md`.
