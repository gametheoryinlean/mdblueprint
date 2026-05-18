---
name: mdblueprint-proof-fill
description: Use when filling a small, local natural-language proof gap inside one existing mdblueprint node. Do not use for new theorem discovery, new lemma generation, or multi-node proof planning.
---

# mdblueprint-proof-fill

Fill a small natural-language proof gap inside a single existing knowledge node.

## When to use

All three conditions must hold before invoking proof-fill:

1. Statement or definition review has **accepted** the target node's statement.
2. Proof review has reported `gap` or `missing proof` for a **small, local** proof step.
3. The required proof can be completed using only the facts already listed in the node's `uses` field, with no new reusable lemmas needed.

Do not invoke proof-fill during statement review, before proof review, when the
proof requires a new reusable lemma, or as a substitute for an available source
proof. If the node has `source.spans`, the Python orchestrator must try
source-proof-recovery first. Proof-fill may receive an explicit source hint from
the orchestrator, but it must not read source files directly.

## Workflow

1. Read the target node: frontmatter, body, and every node listed in `uses`.
2. If the orchestrator provides a source hint, include that hint in the bounded
   prompt. Do not open source files.
3. Call the generator (see `tools/knowledge/templates/proof_fill_generate.md`):
   - package target + allowed dependencies as a bounded context bundle;
   - receive JSON: `decision`, `proof`, `reason`, `used_node_ids`.
4. Validate generator output before proceeding:
   - `decision` must be `filled` or `cannot_fill`;
   - if `filled`, `used_node_ids` must be a subset of the target's `uses` plus the target itself;
   - proof text must not contain placeholders or operational notes;
   - no new lemma/node/dependency proposals.
5. If validation fails or `decision` is `cannot_fill`, stop and write a failure report. Do not edit the node.
6. Call the verifier (see `tools/knowledge/templates/proof_fill_verify.md`) in a **fresh, independent call** with no hidden generator context:
   - include the target node, allowed dependencies, and the candidate proof text;
   - receive JSON: `verdict`, `verification_report`, `repair_hint`.
7. If `verdict` is `gap`, pass `repair_hint` back to the generator for one more repair round (max rounds: 2). Then re-verify.
8. Write back **only** if the final verifier `verdict` is `accepted`:
   - insert the proof text as a `*Proof.*` block in the node body;
   - set `verification.proof: accepted` in the frontmatter if appropriate.
9. On any failure, write a structured report under `docs/knowledge/reviews/`. Do not silently edit the node.

## Forbidden actions

- Creating or proposing new lemma, theorem, proof-plan, or concept nodes.
- Adding new entries to the node's `uses` field.
- Changing the node's statement, title, or kind.
- Changing source metadata.
- Reading source PDFs, books, TeX files, or source spans directly.
- Using mathematical facts not present in the supplied context.
- Running the verifier with the generator's raw context or chain-of-thought visible.

## When to return `cannot_fill`

Stop and report `cannot_fill` when any of the following is true:

- The proof requires a new reusable lemma not already admitted.
- The current `uses` list is insufficient for a valid proof.
- The statement is unclear, disputed, or too strong.
- The proof is not small or local (requires multi-step blueprint exploration).
- Generator output fails validation.
- Verifier returns `critical` (requires human intervention).

## Output locations

- Proof text inserted into node body: existing node file in `docs/knowledge/nodes/` or `docs/knowledge/staged/`.
- Failure or partial reports: `docs/knowledge/reviews/<node_id>_proof_fill_<timestamp>.md`.

## References

- `docs/node-format.md` — node frontmatter and body conventions.
- `docs/math-authoring.md` — supported math syntax for proof text.
- `docs/agent-contracts.md` — proof-fill agent contract.
- `tools/knowledge/templates/proof_fill_generate.md` — generator prompt.
- `tools/knowledge/templates/proof_fill_verify.md` — verifier prompt.
