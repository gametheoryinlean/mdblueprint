---
name: mdblueprint-lean-adjudicate
description: Use when you need to compare Lean-derived theorem and dependency facts against authored EconCSLib nodes, staged drafts, and mdblueprint.yml, then decide whether mismatches are true discrepancies, false abends, or needs-review cases. Use this as the final value-judgment layer after factual extraction.
---

# mdblueprint-lean-adjudicate

Use this skill when the factual Lean pass is already available and you need a final
value judgment against the authored blueprint.

## Scope

- Lean-derived theorem/dependency extraction is the factual layer.
- `nodes/`, `staged/`, and `mdblueprint.yml` are the authored source of truth.
- The judge decides whether a mismatch is:
  - a true discrepancy
  - a false abend caused by granularity, naming, helper lemmas, comments, or formalization artifacts
  - a needs-review case
- Lean can be stronger or weaker than the authored node:
  - stronger Lean means the authored node may be underspecified or missing formalization detail
  - weaker Lean means the authored node may still be the intended contract, and the Lean artifact may be incomplete or `sorry`-backed

## Workflow

1. Read the factual theorem and dependency exports.
2. Map extracted Lean facts onto authored nodes using:
   - declaration names
   - node ids and titles
   - staged metadata
   - filename and namespace hints
3. Compare per node:
   - missing theorem
   - extra theorem
   - missing dependency
   - extra dependency
   - stronger Lean fact than authored node
   - weaker Lean fact than authored node
   - summary-node versus atomic-theorem mismatch
4. Write a case-by-case adjudication report.
5. Decide whether each case is:
   - `accept`
   - `reject`
   - `needs_review`
6. Add a final filter that labels each mismatch as:
   - `true_discrepancy`
   - `false_abend`
   - `needs_review`

## Judgment rules

- Do not treat missing Lean provenance as an inconsistency if the authored node is intentionally informal or `sorry`-backed.
- If Lean is finer-grained than the authored node, prefer `false_abend` unless the semantic intent changes.
- If the authored node is stronger than the Lean fact, flag it as likely incompleteness.
- If the proof contains `sorry`, stubs, or weakened statements, do not call that a true discrepancy unless the authored node requires more.
- Preserve extra formalization lemmas in the report; do not silently discard them.
- Treat definition-node vs theorem-node mapping mistakes as a basic sanity failure, even if the downstream graph is otherwise plausible.
- Use random spot checks to catch silly, obvious mapping mistakes and feed those into targeted fixes.
- Do not silently upgrade heuristic extraction output to ground truth; the final filter must justify the verdict case by case.

## Post-hoc failure modes to score

- `missing_theorem`
- `extra_theorem`
- `missing_dependency`
- `extra_dependency`
- `wrong_node_mapping`
- `many_to_one_mapping`
- `one_to_many_mapping`
- `theorem_strengthened`
- `theorem_weakened`
- `proof_contains_sorry`
- `proof_contains_false_or_stub`
- `comment_leakage`
- `helper_lemma_leakage`
- `accessor_or_notation_false_positive`
- `duplicate_or_collision`
- `dag_violation`
- `summary_node_vs_atomic_theorem_mismatch`
- `formalization_artifact_not_in_authored_graph`
- `true_discrepancy`
- `false_abend`

## Output

Produce:

- a factual extraction summary
- a node-to-theorem mapping table
- a discrepancy table
- a final judgment table with per-node verdicts and confidence
- a final filter table that explicitly labels true discrepancies versus false abends

The report is a review artifact. Do not overwrite authored files automatically.
