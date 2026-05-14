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
```

Body: explanation of extraction decisions, generality questions, uncertainty notes.
