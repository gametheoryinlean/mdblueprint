# Deep Dive: `mechanism_isDSIC`

## Why This Is Representative

`mechanism_design.auction.basic.reserve_second_price_mechanism` is an authored wrapper node whose `uses` list is intentionally small:

- `mechanism_design.auction.basic.second_price_mechanism`
- `mechanism_design.transfer.mechanisms_with_transfers`

The theorem-level extraction for the reserve second-price formalization, however, exposes the local proof structure of the DSIC result rather than only the curated wrapper-level intent.

## Authored Source of Truth

Authored node:

- [`/home/azureuser/EconCSLib/docs/knowledge/nodes/mechanism_design/auction/basic/reserve_second_price_mechanism.md`](file:///home/azureuser/EconCSLib/docs/knowledge/nodes/mechanism_design/auction/basic/reserve_second_price_mechanism.md)

Key authored metadata:

- `id`: `mechanism_design.auction.basic.reserve_second_price_mechanism`
- `kind`: `definition`
- `uses`: `second_price_mechanism`, `mechanisms_with_transfers`
- `lean.declarations`: wrapper definitions plus the local facts ending in `mechanism_isDSIC`

## Source-Theorem View

The Lean file is:

- [`/home/azureuser/EconCSLib/EconCSLib/MechanismDesign/Auction/ReserveVickrey.lean`](file:///home/azureuser/EconCSLib/EconCSLib/MechanismDesign/Auction/ReserveVickrey.lean)

The theorem of interest is:

- `mechanism_isDSIC` at lines 347-354

Its proof is just a one-step reduction:

- it applies `truthful_weakly_dominant`
- then rewrites the mechanism/game equivalence via `game_eq_toStrategicGame`

## Extracted Dependency Shape

The current source-text extractor reports these theorem-level dependencies for `mechanism_isDSIC`:

- `truthful_weakly_dominant`
- `game_eq_toStrategicGame`
- `IsDSIC`
- `isDSIC`
- `IsPositiveAffineOf.symm`
- `Indifferent.symm`

## Failure Mode

This is not a missing-theorem bug like the pre-fix `lam0_le_mu0` issue.

Instead, it is a **projection mismatch**:

1. The authored node is a wrapper summary node.
2. The theorem proof is a generic DSIC reduction theorem that uses proof-local abstractions.
3. The source-text extractor records the local theorem body exactly as written, so it includes generic helper names and proof-shape lemmas.
4. When projected back to the authored node graph, those theorem-level dependencies do not correspond cleanly to the curated `uses` list.

## Practical Consequence

This node should be treated as a wrapper/summary node, not as a pure theorem-local dependency check.

For this class of nodes, the counterchecker should report:

- the wrapper-level authored `uses`
- the theorem-level proof dependencies
- the mismatch as an informational drift signal

but not as a hard inconsistency.

## Takeaway

`mechanism_isDSIC` is a good representative failure mode for the remaining round3 drift:

author-authored summary edges are coarser than theorem-local proof dependencies, so a source-text theorem extractor will naturally surface extra generic lemmas unless a second-stage projection/filter is applied.
