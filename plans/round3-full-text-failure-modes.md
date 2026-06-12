# Round3 Full Run Failure Modes

## Context

This note summarizes the remaining failure modes observed after the source-text-only full rerun at [`runs/round3-full-text-rerun`](../runs/round3-full-text-rerun).

## What Was Fixed

The rerun confirmed that two earlier failure modes were fixed:

- accessor suffixes like `.mp` no longer hide theorem dependencies
- theorem-adjacent comments and doc prose no longer leak extra dependencies such as `singleton_of_card_one`

For `lam0_le_mu0`, the extracted dependency set now matches the requested theorem-local core exactly.

## Remaining Failure Modes

### 1. Theorem-to-node mapping is still many-to-one and many-to-many

A single authored EconCSLib node can map to many theorem records, and many theorem records remain unmapped.

Observed counts:

- authored nodes matched to at least one theorem record: `249`
- theorem records matched to authored nodes: `719`
- theorem records left unmapped: `871`

This means the source-text extractor still produces a theorem graph that is broader than the authored node graph.

### 2. Projection from theorem graph to authored node graph is low precision

After projecting theorem dependencies back onto authored node ids, the resulting graph remains much denser than the curated blueprint graph.

Observed edge statistics:

- projected edges: `963`
- blueprint edges: `840`
- overlapping edges: `154`
- projected-only edges: `809`
- blueprint-only edges: `686`
- precision: `0.1599`
- recall: `0.1833`

This is the dominant remaining mismatch.

### 3. The heuristic still over-collects theorem-adjacent helpers in some files

Even after comment stripping and accessor normalization, the proof-text scanner still admits extra edges because it scans raw theorem text rather than a structured proof AST.

Examples:

- `social_choice.fair_division.cardinal_instance_wrappers` pulled in many divisible and indivisible helper theorems that are not in the authored `uses` list.
- `mechanism_design.auction.basic.reserve_second_price_mechanism` produced a large cluster of auxiliary auction and fair-division theorems.
- `game_theory.strategic_game.strategy_profile` and `mechanism_design.bayesian.bayesian_mechanisms` pulled in large transitive clusters from neighboring concepts.

These are not syntax bugs; they are heuristic recall/precision tradeoffs.

### 4. Some authored nodes are under-extracted because their intended dependencies are conceptual rather than lexical

Examples of authored nodes with missing or incomplete projected uses:

- `math.minimax.loomis_theorem`
- `mechanism_design.vcg.welfare_and_payments`
- `game_theory.extensive_game.theorems_catalog`
- `game_theory.strategic_game.finite_game_catalog`
- `mechanism_design.auction.bayesian.risk_aversion_comparison`

These nodes express higher-level summaries or catalog entries, so the proof text alone is not always enough to reconstruct the authored `uses` set.

### 5. Module-level and namespace-level lexical overlap still causes false positives

Examples:

- `math.simplex.pure` now correctly appears when used, but similar tokens from simplex-related helper files can still inflate neighboring proof graphs.
- `foundation.preference.lottery` and `foundation.preference.indifferent` generate broad cross-links because their proofs share common vocabulary with many downstream nodes.

This is a structural limitation of token-based scanning.

## Implication

The rerun is materially better than the previous one, but the remaining failure modes are now dominated by:

- many-to-one theorem/node alignment ambiguity
- overbroad token matching for proof dependencies
- conceptual authored edges that are not lexically recoverable from source text alone

## Recommended Next Step

Keep the current source-text-only extractor as the baseline, but add a second-stage reducer that:

- filters theorem records to authored node clusters before projection
- separates lexical proof dependencies from summarized conceptual `uses`
- flags catalog / aggregator nodes as expected low-recall cases rather than treating them as normal theorem nodes
