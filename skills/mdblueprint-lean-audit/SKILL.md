---
name: mdblueprint-lean-audit
description: Use to run a coordinator-driven Markdown/Lean alignment audit over a selected set of knowledge nodes. Handles both nodes missing lean: metadata and nodes with existing lean: blocks that need mechanical and semantic checking.
---

# mdblueprint-lean-audit

Coordinate an audit pipeline that checks whether Markdown knowledge nodes are
properly connected to Lean declarations. The coordinator owns all global state,
deterministic indexing, report validation, and file writes. Subagents are
narrow and read-only by default.

## When to use

When auditing a set of knowledge nodes for Lean alignment — whether adding new
`lean:` blocks, checking existing references, or classifying repair scope for
mismatched nodes.

## Context isolation rules

- The coordinator reads and writes files; subagents do not.
- Subagents receive only the bounded bundle the coordinator builds; they must
  not scan the Lean repository directly.
- Subagents must not write `verification.alignment`, `status`, or node files.
- The coordinator validates all subagent outputs before acting on them.

## Coordinator workflow

1. **Load knowledge context.** Call `python -m tools.knowledge.lean_audit
   --list-states <root>` to inspect existing node states, or load the context
   in Python via `KnowledgeContext.load`.

2. **Select target nodes.** Choose the set to audit (e.g. a staged folder,
   all nodes missing `lean:`, or all nodes with `alignment: pending`).

3. **Index Lean repositories.** Run `tools.knowledge.lean_index.index_lean_project`
   for each configured Lean repo. The index is shared across subagent bundles
   but subagents receive only the slice they need.

4. **Determine node audit state.** For each target node call
   `tools.knowledge.lean_audit.determine_node_audit_state`. Nodes in state
   `missing_lean` go to the Link Finder subagent. Nodes in `lean_ref_broken`
   or `lean_ref_ambiguous` go to the Lean Ref Checker. Nodes in
   `pending_alignment` go to the Alignment Verifier. See
   `references/node-audit-states.md` for the full state vocabulary.

5. **Build subagent bundles.** Construct the bounded input bundle for each
   subagent role:
   - Link Finder: `tools.knowledge.lean_link_candidates.build_candidate_bundle`
   - Ref Checker: `tools.knowledge.lean_audit.build_ref_checker_bundle`
   - Alignment Verifier: `tools.knowledge.lean_alignment.build_alignment_bundle`
   - Repair Classifier: combine the node body excerpt + alignment report

6. **Invoke subagents.** Dispatch one bounded bundle per subagent turn.
   Each subagent role is described in the section below and its output schema
   is in `references/`.

7. **Validate subagent outputs.** Call the appropriate validation function
   before acting:
   - `tools.knowledge.lean_audit.validate_ref_checker_output`
   - `tools.knowledge.lean_audit.validate_repair_classifier_output`
   - `tools.knowledge.lean_alignment.validate_alignment_report` (alignment verifier)
   - `tools.knowledge.lean_linking.validate_lean_link_proposal` (link finder)

8. **Write reports and apply small repairs.**
   - For nodes needing Lean generation: `write_needs_lean_report`
   - For alignment verifier output: `write_alignment_report`
   - For repair classification: `write_repair_report`
   - For validated `link` proposals: `apply_lean_link_proposal` (allowed only
     when the proposal is unique, mechanical, and validated)

9. **Large revisions require user confirmation.** Do not apply any change to
   mathematical statements, hypotheses, definitions, proofs, `uses`, or Lean
   code without explicit user approval.

## Subagent roles

### Link Finder

Purpose: propose a `lean:` block for a node with no existing lean metadata.

Input bundle: built by `build_candidate_bundle` from
`tools.knowledge.lean_link_candidates`.

Output schema: see `mdblueprint-lean-linking` skill (`skills/
mdblueprint-lean-linking/SKILL.md`).

Rules:
- Returns `link | no_match | ambiguous | needs_lean_generation | needs_human_decision`.
- Must not claim semantic alignment.
- Must not set `verification.alignment`.
- Must not edit node files.

### Lean Ref Checker

Purpose: mechanically verify an existing `lean:` block and classify
declaration roles.

Input bundle: built by `build_ref_checker_bundle`.

Output schema: `references/lean-ref-checker-schema.md`.

Rules:
- Reads only the bounded declaration metadata supplied by the coordinator.
- Does not scan the whole Lean repository.
- Does not perform semantic alignment.
- Must not set `status`, `verification`, or `lean` in the output.

### Alignment Verifier

Purpose: semantically compare one Markdown node with one resolved Lean
declaration.

Input bundle: built by `build_alignment_bundle` from
`tools.knowledge.lean_alignment`.

Output schema: `skills/mdblueprint-alignment-review/references/
alignment-report-schema.md`.

Rules:
- Reads only the bounded bundle.
- Returns a structured alignment classification.
- Must not update node frontmatter or status directly.

### Repair Classifier

Purpose: classify the scope of a repair needed to fix a misaligned node.

Input bundle: node body excerpt + alignment report + repair policy.

Output schema: `references/repair-classifier-schema.md`.

Rules:
- Returns `small_fix | large_revision | cannot_fix | needs_user_hint`.
- Must not produce patches or diffs.
- Must classify any change to a mathematical statement, hypothesis, definition,
  proof, `uses` dependency, or Lean code as `large_revision`.

## Report outputs

All reports go to `docs/knowledge/reviews/` or `docs/knowledge/requests/`.
Do not write process history into node bodies.

```text
docs/knowledge/reviews/<node_id>_lean_alignment_<timestamp>.md
docs/knowledge/reviews/<node_id>_alignment_repair_<timestamp>.md
docs/knowledge/requests/<node_id>_needs_lean_<timestamp>.md
```

## Non-goals

- Do not build an unconstrained agent that scans the whole Lean repository.
- Do not let the Alignment Verifier rewrite Markdown statements.
- Do not treat mechanical Lean reference existence as semantic alignment.
- Do not auto-repair mathematical mismatches without explicit user confirmation.
