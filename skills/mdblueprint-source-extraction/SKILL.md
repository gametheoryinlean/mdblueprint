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
2. Read `docs/knowledge/mdblueprint.yml`. If `topics` is configured, select a canonical topic id from the registry. Do NOT invent new top-level topic prefixes; if no existing topic fits, record the gap in the extraction report.
3. Read the source material and identify mathematical content: definitions, theorems, lemmas, examples, proof ideas.
4. For each item, search the existing node index (admitted + staged) for duplicates.
5. If no duplicate, create a staged node under `docs/knowledge/staged/` following the node format, using the canonical topic prefix from the registry. If the intended prefix is an alias, use the canonical id and note the alias in the report.
6. Record source spans with artifact binding and locator format.
7. Convert formulas to the supported node math syntax in `docs/math-authoring.md`; declare reusable macros in project config instead of writing TeX preamble commands.
8. If the source statement appears narrower than the reusable mathematical form, note a generality question — do not assert the broader form as truth.
9. Write an extraction report under `docs/knowledge/reviews/`.

## Book and PDF extraction checklist

- Record the book or PDF path as a source artifact before extracting nodes.
- Capture precise locators: chapter, section, theorem number, definition number, page, or URL fragment.
- Preserve the statement as written unless the task explicitly asks for normalization.
- Preserve mathematical notation, but use supported mdblueprint delimiters and configured macros.
- Put any proposed generalization in the report, not in admitted truth.
- Extract dependencies only when the source or existing node index justifies them.
- Prefer several small staged nodes over one merged node containing multiple concepts.

## Rules

- Write staged candidates only. Never write to `docs/knowledge/nodes/`.
- Do not invent dependencies beyond what the source or node index justifies.
- Check for near-duplicates before creating a new staged file.
- Preserve source-local statements; propose normalizations as questions.
- **Stop after writing the extraction report.** Do not invoke node-review or wait for it. The handoff is the report artifact.
- If the source material is large, split it into bounded batches (one per extraction run) before processing. Stop with a partial report rather than consuming unbounded context.
- Do not loop, wait for another agent, or recursively invoke another skill. Each run is one-shot.

## Report format

See `references/extraction-report-schema.md`.
