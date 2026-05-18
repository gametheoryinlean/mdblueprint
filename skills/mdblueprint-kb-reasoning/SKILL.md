---
name: mdblueprint-kb-reasoning
description: Use when answering questions from admitted mdblueprint knowledge nodes without using Lean source, source PDFs, implementation files, internet, or model memory as evidence.
---

# mdblueprint-kb-reasoning

Reason only from a deterministic KB context bundle.

## Required Mode

Use the context packer before answering:

```bash
uv run python -m tools.knowledge.context_pack docs/knowledge --target <node-id>
uv run python -m tools.knowledge.context_pack docs/knowledge --topic <topic-id>
```

By default, the bundle contains admitted nodes only. Add `--include-staged` only
when the user explicitly asks for non-admitted evidence, and label that evidence
as provisional.

## Allowed Evidence

- `docs/knowledge/nodes/**/*.md`
- `docs/knowledge/mdblueprint.yml`
- exact `topics.md` catalogs when they affect retrieval or display
- deterministic graph/index data derived from those nodes

## Forbidden Evidence

- Lean source files;
- source PDFs/books/TeX files;
- implementation files outside the generated bundle;
- internet access;
- uncited model memory.

## Answer Contract

- Cite node ids for every KB claim.
- Say when the bundle lacks a fact instead of filling it from outside knowledge.
- If a missing fact seems important, propose a request or staged-node task.
- Do not edit files unless the user explicitly asks for a KB change.

