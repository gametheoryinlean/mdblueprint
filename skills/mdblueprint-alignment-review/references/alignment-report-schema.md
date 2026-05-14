# Alignment Report Schema

```yaml
agent: alignment-verifier
target:
  node_id: <node.id>
  path: <path to node file>
decision: aligned | lean_stronger | lean_weaker | lean_special_case | lean_extra_hypotheses | lean_missing_hypotheses | definition_mismatch | uncertain
created_at: "ISO-8601"
inputs:
  - <node file path>
  - <lean declaration source>
summary: <one sentence>
prechecks:
  modules_found: true | false
  declarations_found: true | false
  sorry_present: true | false
```

Body: detailed comparison of Markdown statement vs Lean signature, noting extra/missing hypotheses, specializations, etc.
