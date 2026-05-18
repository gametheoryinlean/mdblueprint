# Extraction Report Schema

```yaml
agent: source-to-md
target:
  path: docs/knowledge/staged/<filename>.md
decision: extracted | partial | uncertain | blocked
created_at: "ISO-8601"
inputs:
  - <source artifact path or identifier>
summary: <one sentence>
proof_status: full | partial | absent | not_extracted
dependency_alignment:
  existing_uses:
    - node_id: <existing admitted or staged node id>
      reason: <why the source proof logically uses this fact>
      source_locator: <page/section/theorem/paragraph>
  missing_dependencies:
    - description: <missing reusable lemma/definition/fact>
      source_locator: <page/section/theorem/paragraph>
      request_path: docs/knowledge/requests/<request-file>.md | null
```

Body: explanation of extraction decisions, generality questions, proof extraction
status, dependency alignment, and uncertainty notes.

`proof_status` values:

- `full`: the staged node includes a `*Proof.*` block derived from the source proof.
- `partial`: the staged node preserves the extractable proof text, but the report
  records gaps, hidden background facts, or source incompleteness.
- `absent`: the source item has no proof text.
- `not_extracted`: the source has proof text, but extraction did not include it;
  the report must state the reason.

Dependency alignment contract:

- Search both admitted nodes and staged nodes before choosing `uses`.
- Add an existing node id to `uses` only when it is a logical dependency of the
  extracted proof.
- Record missing reusable facts under `missing_dependencies`. When practical,
  create a matching request under `docs/knowledge/requests/` and set
  `request_path`.
- Extraction must not set `verification.proof: accepted`; proof review remains a
  separate gate.
