# Heuristic Countercheck Methodology

## Purpose

Document the heuristic path used to countercheck Lean-derived theorem graphs against authored nodes.

This note covers:

- how theorem names are extracted from Lean source text
- how node declarations are matched to Lean declarations
- how dependency candidates are reduced to likely theorem-to-theorem edges
- how false positives are controlled

## Input Sources

- authored node file under `docs/knowledge/nodes/`
- Lean source file under `EconCSLib/`
- authored `uses` hints from the node frontmatter
- a corpus-wide theorem-name index built from Lean source text

## Heuristic Extraction Procedure

1. Read the Lean file as plain text.
2. Detect theorem-like declarations with a conservative regex over `theorem`, `lemma`, `def`, `abbrev`, and `example`.
3. Build a theorem-name corpus from the full Lean tree so the extractor only considers names that actually exist in the project.
4. For each declaration body, search for theorem-like names that appear in the proof text.
5. Emit only theorem-to-theorem edges; do not keep Mathlib or tactic names as graph nodes.
6. Compare the result against the authored node frontmatter.

## Normalization Procedure

To make authored hints line up with Lean names, the comparer normalizes both sides with these rules:

- lowercase both names
- remove punctuation and separator characters
- compare normalized full names
- compare normalized basenames as a fallback

This allows authored hints such as `strategic_games.weakly_dominates` to match Lean names such as `WeaklyDominates`.

## False-Positive Reductions

The following filters were added to keep the heuristic output from becoming tactic-noise:

- stopword filtering for tactic words and proof scaffolding such as `exact`, `intro`, `simp`, `by_cases`, and `apply`
- minimum length / shape checks for candidate names
- longest-first matching so longer theorem names are preferred over shorter substrings
- same-file restriction when building candidate targets unless a broader corpus pass is explicitly needed
- deduplication of extracted edges
- node-parser loading for Markdown frontmatter instead of raw YAML parsing the entire node file

## Smoke-Test Result

Sample:

- node: `strategic_games.weakly_dominant_strategy`
- Lean file: `EconCSLib/GameTheory/StrategicGame/Dominance.lean`

Observed after normalization and filtering:

- matched declarations: `StrategicGame.IsWeaklyDominant`
- missing uses: `(none)`
- extra uses were limited to theorem-like names only, rather than tactic words or single-letter identifiers

The most recent smoke run produced:

- `missing_uses = []`
- `extra_uses = ['IsBestResponse', 'IsStrictlyDominant', 'IsWeaklyDominant', 'Profile', 'Strategy']`
- `matched_declarations = ['StrategicGame.IsWeaklyDominant']`

## Notes

- The heuristic path remains useful as a fallback and a baseline.
- The heuristic report is intentionally conservative: it prefers fewer false positives over exhaustive dependency coverage.
