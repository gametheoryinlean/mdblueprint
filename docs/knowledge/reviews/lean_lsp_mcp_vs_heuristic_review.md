---
agent: lean-countercheck
created_at: "2026-06-12T04:34:00+00:00"
title: lean-lsp-mcp vs heuristic extraction review
---

# lean-lsp-mcp vs Heuristic Extraction Review

## Scope

This review records the first-pass countercheck work for the new `mdblueprint-lean-countercheck` flow.

The repo-side source of truth remains the authored blueprint material:

- `docs/knowledge/nodes/`
- `docs/knowledge/staged/`
- `docs/knowledge/mdblueprint.yml`

Lean is treated as a counterchecker only.

## What Was Implemented

- A local countercheck CLI: `mdblueprint-lean-countercheck`
- Markdown-node parsing via the existing node parser instead of raw YAML loading
- Source-text theorem extraction from Lean monoliths
- Proof-local dependency extraction filtered to theorem-like names
- `lean-lsp-mcp` availability probing via `uvx lean-lsp-mcp --help`
- Countercheck reports written to `docs/knowledge/reviews/`

## Smoke-Test Result

Sample checked:

- node: `strategic_games.weakly_dominant_strategy`
- Lean file: `EconCSLib/GameTheory/StrategicGame/Dominance.lean`

Observed result in the corrected report:

- matched declaration: `StrategicGame.IsWeaklyDominant`
- missing declarations: none
- missing uses: none after snake_case / CamelCase normalization
- extra declarations: supporting theorem names from the Lean file, which are useful proposals for review

Corrected report artifact:

- `docs/knowledge/reviews/strategic_games_weakly_dominant_strategy_lean_countercheck_2026-06-12T04_32_16_00_00.md`

## Value-Add of `lean-lsp-mcp`

`lean-lsp-mcp` is worth keeping as a first-class option because it gives a structured Lean-aware path when local source heuristics get brittle.

Expected benefits:

- fewer ad hoc parsing assumptions than pure regex extraction
- better theorem-name and proof-context recovery once fully wired in
- a clearer path for disambiguating nodes that correspond to multiple Lean theorems
- lower maintenance risk than depending only on heuristic text parsing

## Why the Heuristic Fallback Still Matters

The heuristic source-text path remains useful because it:

- works without a running language server
- can be used for quick smoke tests
- remains a fallback when `lean-lsp-mcp` setup is unavailable

The local smoke test also showed that the heuristic layer needed normalization to match authored node hints like `strategic_games.weakly_dominates` against Lean names like `WeaklyDominates`.

## Recommendation

Use `lean-lsp-mcp` as the preferred experimental path when the goal is structured theorem recovery, but keep heuristic extraction as the fallback and comparison baseline.

The current repository review is intentionally conservative: it documents setup, smoke-test behavior, and the practical reasons to prefer the language-server path without claiming a full end-to-end MCP extraction has already been integrated here.


## Status Update

`lean-lsp-mcp` is currently deprioritized. The local workflow still requires a warm Lean project state, and the `lake build` prerequisite makes the path too heavy for the near-term agenda. The heuristic extractor remains the active baseline.
