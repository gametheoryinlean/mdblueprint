---
name: mdblueprint-source-proof-recovery
description: Use when an existing mdblueprint theorem-like node has missing or incomplete proof content and the repair should return to cited source spans or source hints.
---

# mdblueprint-source-proof-recovery

Recover proof evidence for one existing theorem-like node from its cited source.
This is not source extraction, proof-fill, proof review, or admission.

## When To Use

Use when the target node is a lemma, proposition, theorem, or external-theorem
with missing/incomplete proof content, `verification.proof: gap`, or a recovery
request, and it has `source.spans` or an orchestrator-provided source location.

Do not use for creating new staged nodes from a source batch. Use
`mdblueprint-source-extraction` for that.

## Allowed Reads

- target node frontmatter and body;
- bodies of nodes already listed in target `uses`;
- admitted and staged node index for dependency lookup;
- cited source spans only, not unrelated source material;
- topic catalog/config only when needed for dependency requests.

## Allowed Writes

- for staged nodes: a proposed `*Proof.*` block when the Python orchestrator
  grants a write path;
- source-proof-recovery reports under `docs/knowledge/reviews/`;
- missing dependency requests under `docs/knowledge/requests/`;
- for admitted nodes: a recovery report or staged revision proposal by default.

## Workflow

1. Confirm the target is theorem-like and has missing/incomplete proof content.
2. Read only the bounded target/dependency/source-span bundle supplied by the
   Python orchestrator.
3. Classify the source evidence as full proof, partial proof, hint only, no
   useful proof evidence, or blocked.
4. If proof text exists, normalize it to mdblueprint Markdown while preserving
   the source argument.
5. Map proof steps to existing admitted or staged dependencies; add no invented
   dependencies.
6. For missing reusable dependencies, write a request or report entry.
7. Output a structured report and stop.

Report decision vocabulary:

```text
decision: recovered | partial | hint_only | not_found | blocked
```

## Forbidden Actions

- Do not set `verification.proof: accepted`.
- Do not admit nodes or move files into `docs/knowledge/nodes/`.
- Do not silently broaden or change the statement.
- Do not read beyond cited source spans unless the orchestrator explicitly
  supplies an expanded source bundle.
- Do not invoke proof-fill, proof review, or admission. A source hint may be
  passed onward by the Python orchestrator, but this skill does not call
  proof-fill itself.
