---
name: mdblueprint-lean-dependency-extraction
description: Use when reading Lean source text to recover theorem-to-theorem dependencies from proof text, ignoring Mathlib and kernel support terms unless they appear as theorem names in the proof itself.
---

# mdblueprint-lean-dependency-extraction

Extract theorem dependencies from Lean source by reading proof text and matching theorem names actually used in the proof.

## Inputs

- theorem-name records from `mdblueprint-lean-theorem-extraction`
- Lean project root
- source root
- one Lean file or bounded Lean file set

## Output

- theorem-to-theorem dependency edges
- proof-local evidence from the source text
- optional source declaration metadata

## Rules

- Use source-text proof bodies and theorem mentions as the primary signal.
- Do not infer file-level dependencies.
- Do not record Mathlib or kernel dependencies unless they are explicitly theorem names used in the proof and belong in the theorem graph.
- Do not use Lean elaboration as the default path.
- Do not rewrite node files.
- Keep theorem dependency edges separate from blueprint materialization.

## Validation

- Cross-check a sample theorem manually against its proof text.
- Verify that obvious proof-local dependencies appear and imported-support artifacts do not.
- If a proof is ambiguous, keep the edge set conservative and defer to a fallback validation pass.

## Next stage

- pass theorem records and theorem dependency edges to `mdblueprint-lean-node-generation`
