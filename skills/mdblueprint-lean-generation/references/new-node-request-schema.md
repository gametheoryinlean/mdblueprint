# New-Node Request Schema

```yaml
request_id: <unique string>
kind: new-node | split-node | generalize-node | missing-dependency | lean-bridge
requested_by: lean-generator
created_at: "ISO-8601"
target_kind: <definition | lemma | theorem | ...>
proposed_id: <candidate.node.id>
proposed_title: <one-line title>
summary: <one sentence>
reason: |
  Why existing nodes are insufficient.
proposed_statement: |
  The most general useful form of the proposed content.
proposed_uses:
  - <dependency node ids>
source_justification: |
  Why this should be a reusable node rather than a local Lean lemma.
```
