---
name: mdblueprint-source-extraction
description: Use when extracting candidate mdblueprint knowledge nodes from PDFs, books, papers, TeX source, lecture notes, or other source material.
---

# mdblueprint-source-extraction

Extract candidate knowledge nodes from PDFs, books, papers, TeX, or notes.

## When to use

When converting source material into staged Markdown knowledge nodes.

## Workflow

1. Identify the source artifact and create a manifest entry.
2. Read the source material and identify mathematical content: definitions, theorems, lemmas, examples, proof ideas.
3. For each item, search the existing node index (admitted + staged) for duplicates.
4. If no duplicate, create a staged node under `docs/knowledge/staged/` following the node format.
5. Record source spans with artifact binding and locator format.
6. If the source statement appears narrower than the reusable mathematical form, note a generality question — do not assert the broader form as truth.
7. Write an extraction report under `docs/knowledge/reviews/`.

## Book and PDF extraction checklist

- Record the book or PDF path as a source artifact before extracting nodes.
- Capture precise locators: chapter, section, theorem number, definition number, page, or URL fragment.
- Preserve the statement as written unless the task explicitly asks for normalization.
- Put any proposed generalization in the report, not in admitted truth.
- Extract dependencies only when the source or existing node index justifies them.
- Prefer several small staged nodes over one merged node containing multiple concepts.

## Rules

- Write staged candidates only. Never write to `docs/knowledge/nodes/`.
- Do not invent dependencies beyond what the source or node index justifies.
- Check for near-duplicates before creating a new staged file.
- Preserve source-local statements; propose normalizations as questions.

## Report format

See `references/extraction-report-schema.md`.
