# Formulation-Sensitive Impact Analysis

Use this reference when a graph refactor modifies, weakens, strengthens,
replaces, or deletes a node or dependency.

## Principle

Reachability in the dependency DAG says which descendants might be affected. It
does not say how much the change percolates. A descendant may remain valid,
require only a proof repair, need a weaker statement, split into cases, or fail
entirely depending on the exact formulations of its other ancestors.

Treat this as a high-impact semantic review, not a mechanical cleanup.

## Procedure

1. Name the changed item: node id, dependency edge, topic move, or merge/split.
2. List affected descendants and the paths by which they reach the changed item.
3. Classify the role of the changed item:
   - definition or notation;
   - axiom, assumption, or existence principle;
   - equivalence between formulations;
   - construction used in a proof;
   - bridge lemma between topics or formalizations;
   - Lean-only or source-only support.
4. For each important descendant, inspect its statement, proof text, `uses`, and
   other ancestors. Ask:
   - Does another ancestor already carry a formulation strong enough to replace
     the changed item?
   - Are two definitions equivalent only under the changed item?
   - Does the theorem remain true while the recorded proof route breaks?
   - Does the statement need a weaker conclusion or extra hypothesis?
   - Should the node split into formulation-specific variants?
5. Choose the least-bloated useful response:
   - no action, with reason;
   - proof-review or proof-fill request;
   - dependency retargeting to an existing ancestor;
   - missing bridge/equivalence request;
   - split-node or generalize-node request;
   - `needs-human-review` when the formulation choice is mathematical policy.

## Anti-Bloat Rules

- Do not introduce every possible alternate formulation as a node.
- Add a bridge or equivalence node only when it is reusable, affects several
  descendants, blocks admission/formalization, or marks a real mathematical
  boundary.
- Prefer one clear human decision over many speculative requests.
- If source or Lean evidence is needed but not in the bundle, mark the proposal
  `blocked` or `needs-human-review` instead of filling the gap from memory.

## Report Notes

For durable reports, record:

- descendant ids reviewed;
- ancestor formulations that may preserve the claim;
- affected status: `unchanged`, `proof_needs_repair`, `statement_weakens`,
  `definition_diverges`, `split_recommended`, or `blocked`;
- requested bridge, split, or generalization files if any;
- validation commands to run after the proposed change.
