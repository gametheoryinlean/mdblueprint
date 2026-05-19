# Alignment Report Schema

```yaml
agent: alignment-verifier
node_id: <node.id>
repository: <repo id>
declaration: <fully qualified Lean declaration>
classification: aligned | lean_stronger | lean_weaker | lean_special_case | lean_extra_hypotheses | lean_missing_hypotheses | definition_mismatch | uncertain
evidence:
  - markdown: <quoted Markdown phrase or formula>
    lean: <quoted Lean signature/snippet phrase>
    note: <why this supports the classification>
risks:
  - <semantic risk, mismatch, or caveat>
recommendation: <one sentence>
```

The report is produced from a bounded Python bundle. The agent must not scan the
whole Lean repository and must not set `verification.alignment` directly.
