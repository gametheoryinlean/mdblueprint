# Lean Ref Checker Output Schema

The Lean Ref Checker receives a bounded bundle of one node's `lean:` block
plus the indexed metadata for only the referenced declarations. It returns a
structured status and optional role classification.

## Output

```yaml
agent: lean-ref-checker
node_id: <node.id>
status: resolved | broken | ambiguous | suspicious
declarations:
  - declaration: <fully qualified Lean name>
    role: primary_definition | theorem_statement | projection | helper | notation | instance
notes: "<optional explanation>"
```

## Field rules

- `agent` must be `lean-ref-checker`.
- `status` must be one of `resolved | broken | ambiguous | suspicious`.
- `declarations` is a list of declaration/role pairs for the declarations
  the coordinator supplied. Omit entries for declarations that could not be
  resolved.
- `role` is required only when `status: resolved`. Valid values:
  - `primary_definition` — the main definition or theorem the node represents
  - `theorem_statement` — the theorem the node's body states
  - `projection` — a field accessor or projection of a structure
  - `helper` — an auxiliary lemma or definition used by the primary
  - `notation` — a notation alias
  - `instance` — a type class instance
- `notes` is a free-text field for explaining `suspicious` status or caveats.

## Constraints

The Lean Ref Checker must not:
- Scan the Lean repository beyond the supplied bundle.
- Set `status`, `verification`, `lean`, or any frontmatter fields in its output.
- Perform semantic alignment (that is the Alignment Verifier's role).
- Return `status: resolved` if any declaration in the bundle is missing or
  unresolvable.
