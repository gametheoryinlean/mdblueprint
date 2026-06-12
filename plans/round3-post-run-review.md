# Round3 Post-Run Review

This note consolidates the main items to inspect after the round3 source-text run.

## Candidate node clusters

These authored nodes are the clearest places to review because they either split into many Lean theorem records or appear to carry wrapper-style semantics:

- `social_choice.fair_division.cardinal_instance_wrappers`
- `mechanism_design.bayesian.bayesian_mechanisms`
- `game_theory.strategic_game.core.mixed_strategy`
- `game_theory.extensive_game.equilibrium.reached_subgame_nash_restriction`
- `game_theory.strategic_game.zero_sum.lam_mu_existence`
- `mechanism_design.auction.optimal_single_item`
- `mechanism_design.auction.bayesian_single_item`
- `math.fixed_point.scarf`
- `market_design.matching.gale_shapley`
- `game_theory.extensive_game.behavior_strategy`
- `social_choice.voting.basic`

## Candidate edge failure modes

These are the main edge-level issues to inspect in the projected theorem graph:

- theorem-local proof helpers that are broader than authored `uses` lists
- wrapper nodes whose Lean theorem proof is finer-grained than the authored node
- proof-text leakage from comments or adjacent prose
- accessor-normalization misses such as `.mp` or `.mpr`
- theorem-vs-definition mapping mistakes that should be treated as sanity checks, not hard failures
- many-to-one node mapping and one-to-many theorem mapping

## Explicitly non-fatal cases

These should be recorded, not automatically rejected:

- extra formalization lemmas introduced by Lean
- stronger Lean facts than the authored node, when the authored node is a wrapper or summary
- weaker Lean facts when the authored node is intentionally incomplete or `sorry`-backed
- legitimate wrapper-style theorem-to-definition mappings

## Reports to consult

- [`round3-node-theorem-crosswalk.md`](round3-node-theorem-crosswalk.md)
- [`round3-full-text-failure-modes.md`](round3-full-text-failure-modes.md)
- [`round3-failure-mode-deep-dive-mechanism_isDSIC.md`](round3-failure-mode-deep-dive-mechanism_isDSIC.md)
- [`lam0_le_mu0-audit.md`](lam0_le_mu0-audit.md)

## Current interpretation

The round3 source-text pass is useful as a countercheck and review aid, but it does not replace the authored EconCSLib / blueprint graph. Use the theorem-level output to flag suspicious nodes and edges, then let the adjudication layer decide whether each case is a true discrepancy, false abend, or needs-review item.
