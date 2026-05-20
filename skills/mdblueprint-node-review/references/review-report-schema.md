# Review Report Schema

## Statement/Definition Verifier Report

```yaml
agent: statement-verifier
target:
  node_id: <node.id>
  path: <path to node file>
decision: accepted | needs_revision | rejected
created_at: "ISO-8601"
inputs:
  - <node file path>
  - <dependency node paths>
summary: <one sentence>
semantic_audit:
  formal_core: pass | fail
  non_descriptive: pass | fail
  dependency_grounding: pass | fail | unverifiable
  source_reference: pass | fail | waived
  lean_link_vs_alignment: pass | fail | not_applicable
  notes: "<optional explanation of any failure>"
generality:
  reviewed: true
  prompt: "<generality question>"
  verdict: "<answer>"
```

All five `semantic_audit` fields are required. Use `not_applicable` for
`lean_link_vs_alignment` when the node has neither a `lean:` block nor
`verification.alignment`. Use `waived` for `source_reference` when the project
does not require source spans (see `semantic-audit-rubric.md` Gate 4).

## Proof Verifier Report

```yaml
agent: proof-verifier
target:
  node_id: <node.id>
  path: <path to node file>
decision: accepted | gap | critical
created_at: "ISO-8601"
inputs:
  - <node file path>
  - <dependency node paths>
summary: <one sentence>
gaps:
  - description: "<what is missing>"
    dependency: "<node id or argument>"
```

## Admission Referee Report

```yaml
agent: admission-referee
target:
  node_id: <node.id>
  path: <path to staged node>
decision: admit | needs_revision | needs_human_decision | reject
created_at: "ISO-8601"
inputs:
  - <statement verifier report>
  - <proof verifier report if applicable>
  - <generality gate answer>
  - <python check output>
summary: <one sentence>
```
