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
generality:
  reviewed: true
  prompt: "<generality question>"
  verdict: "<answer>"
```

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
