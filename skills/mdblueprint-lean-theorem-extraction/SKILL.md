---
name: mdblueprint-lean-theorem-extraction
description: Use when reading Lean source text to identify theorem, lemma, proposition, and example names, proof spans, and module metadata without Lean elaboration.
---

# mdblueprint-lean-theorem-extraction

Extract theorem-like names directly from Lean source text.

## Inputs

- one Lean file or a bounded Lean file set
- source root
- optional module metadata or file list for validation

## Output

- theorem, lemma, proposition, and example names
- declaration kinds when detectable from text
- file path and line ranges
- lightweight proof-span markers when available

## Rules

- Read the Lean file text directly first.
- Prefer conservative matching over recall: missing a borderline declaration is better than inventing one.
- Regex may be used as a bootstrap, but validate it on a small sample before batch extraction.
- Do not require Lean elaboration for the primary pass.
- Keep Mathlib and kernel artifacts out of the discovery stage unless needed for validation.
- Do not draft Markdown nodes here.

## Validation

- Test the extractor on a small file with known theorem counts.
- Compare discovered names against a manual pass or a reviewed sample.
- If the source-text pass is unstable on a pattern, record the pattern and defer it to the fallback Lean-based path.

## Next stage

- pass the theorem-name records to `mdblueprint-lean-dependency-extraction`
