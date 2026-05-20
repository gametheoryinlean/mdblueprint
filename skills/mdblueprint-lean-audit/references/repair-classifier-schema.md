# Repair Classifier Output Schema

The Repair Classifier receives a bounded bundle containing one Markdown node
body excerpt plus the alignment report from the Alignment Verifier. It returns
a structured repair scope classification.

## Output

```yaml
agent: repair-classifier
node_id: <node.id>
decision: small_fix | large_revision | cannot_fix | needs_user_hint
reason: "<one sentence explaining the decision>"
proposed_changes:
  - field: <field name>
    description: "<what would change>"
```

## Decision vocabulary

- `small_fix` — the repair is a mechanical metadata change only (e.g. adding a
  missing module path or correcting a fully qualified declaration name). No
  mathematical content changes.
- `large_revision` — the repair requires changing a mathematical statement,
  hypothesis, definition, proof body, `uses` dependency, or Lean code.
  **Requires explicit user confirmation before the coordinator may apply it.**
- `cannot_fix` — the misalignment cannot be repaired without new Lean code or
  a new mathematical statement that the repair classifier cannot produce.
- `needs_user_hint` — the intent of the Markdown node or the Lean declaration
  is ambiguous; the user must clarify before repair can proceed.

## Constraints

The Repair Classifier must not:
- Produce a `patch`, `diff`, or direct file edit instruction.
- Apply any change to node files directly.
- Classify a change to any of the following fields as `small_fix`:
  - `statement` or `conclusion`
  - `hypotheses`
  - `definition`
  - `proof`
  - `uses`
  - `lean_code`
  - `theorem`
  These fields always require `large_revision`.

## `proposed_changes` field

The `proposed_changes` list is optional. When present, each entry names the
field that would change and gives a short description. This is read by the
coordinator when deciding whether to surface the repair for user review.

If `decision: large_revision` or `cannot_fix`, `proposed_changes` may be
omitted; the `reason` field alone is sufficient.
