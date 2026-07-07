---
name: mdblueprint-lean-countercheck
description: Use when comparing Lean-derived theorem graphs against authored nodes, staged drafts, and mdblueprint.yml using source-text extraction and conservative normalization.
---

# mdblueprint-lean-countercheck

Compare Lean-derived theorem graphs against authored nodes, staged drafts, and `mdblueprint.yml`.

## Goals

- countercheck authored nodes against theorem names extracted from Lean source text
- surface drift, missing edges, and newly introduced lemmata for review
- keep the authored blueprint authoritative

## What to compare

- theorem-name extraction from Lean source text
- proof-local dependency extraction from theorems
- node/frontmatter declarations and `uses`
- `nodes/`, `staged/`, and `mdblueprint.yml` as the source of truth

## Heuristic path

- Read Lean files directly.
- Extract theorem, lemma, proposition, example, def, and abbrev names conservatively.
- Use proof text to infer theorem-local dependencies.
- Compare the result against authored node metadata.

## Normalization

Use conservative matching when comparing authored hints against Lean names:

- lowercase both sides
- strip punctuation and separators
- compare normalized full names
- compare normalized basenames as a fallback

This helps authored hints like `algebra.group_hom` match Lean names like `GroupHom`.

## False-positive control

- filter tactic words and proof scaffolding
- prefer longest theorem names first
- deduplicate extracted dependencies
- treat blank or flawed proofs as incompleteness, not inconsistency


## Batching note

The CLI is designed around one authored node and one Lean file at a time.
If you need to compare many nodes, use the repo batch driver
`tools.knowledge.lean_countercheck_batch`. It calls `build_name_corpus(...)`
once, then loops over node/file pairs using the precomputed corpus names.
Do not rebuild the full corpus inside each loop iteration; that turns a quick
countercheck into a slow repeated scan.

## Output

Generate a countercheck report that lists:

- matched declarations
- missing declarations
- extra declarations
- missing uses
- extra uses
- warnings or drift proposals

Keep the report as a review artifact. Do not overwrite authored files automatically.
