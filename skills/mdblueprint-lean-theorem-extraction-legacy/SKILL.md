---
name: mdblueprint-lean-theorem-extraction-legacy
description: Deprioritized fallback for compiling Lean source to enumerate theorem-like declarations when source-text extraction is insufficient.
---

# mdblueprint-lean-theorem-extraction-legacy

Extract theorem-like declarations from Lean source by compiling the file in its Lean project context and reading the elaborated environment.

This path is a fallback. Prefer source-text theorem-name extraction for new
runs unless Lean elaboration is explicitly required for validation.

## Inputs

- one Lean file or bounded Lean file set
- Lean project root
- source root used to derive module names

## Output

- declaration records
- module name
- declaration kinds
- type strings
- declaration ranges when available

## Rules

- Use Lean compilation output or Lean APIs only.
- Do not use regex or natural-language parsing.
- Do not scan unrelated Lean files.
- Do not draft Markdown nodes in this step.
- Keep the result as structured data for the next stage.

## Use sparingly

- Prefer `mdblueprint-lean-theorem-extraction` for routine theorem-name discovery.
- Use this fallback only when a source-text pass cannot resolve a file cleanly.

## Next stage

- pass the extracted theorem records to `mdblueprint-lean-dependency-extraction` if Lean validation is needed
