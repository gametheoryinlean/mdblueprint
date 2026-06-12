# lam0_le_mu0 Audit

## Scope

Audit the theorem-local dependencies for [`lam0_le_mu0`](file:///home/azureuser/EconCSLib/EconCSLib/Math/Minimax/MinimaxLoomis.lean) against the current round3 source-text extraction.

## Source Proof

The proof body at lines 194-203 of `MinimaxLoomis.lean` uses the following helper lemmas explicitly:

- `exists_xx_lam0`
- `exists_yy_mu0`
- `wsum_wsum_comm`
- `ge_iff_simplex_ge`
- `le_iff_simplex_le`

## Root Cause

The node-side declaration list for `game_theory.strategic_game.zero_sum.lam_mu_existence` is not the failure mode. The authored node already points at the intended Loomis cluster, and the theorem names on the node are not inflated with unrelated helpers.

The failure is in dependency extraction:

- the proof text uses accessor-form names such as `ge_iff_simplex_ge.mp` and `le_iff_simplex_le.mp`
- the previous heuristic only resolved the full token or the final suffix, so `mp` was treated as the base name and the theorem names were missed
- the extractor also over-approximates dependencies by scanning raw proof text, so it picked up theorem-adjacent helpers like `singleton_of_card_one`, `stdSimplex.pure`, `Lottery.pure`, and `Strategy`

The fix was to strip accessor suffixes before lookup. After that change, the mandatory lemmas are recovered, but the extractor is still over-inclusive on auxiliary helpers.

## Extracted Dependencies

The extracted theorem record for `lam0_le_mu0` currently lists exactly:

- `exists_xx_lam0`
- `exists_yy_mu0`
- `wsum_wsum_comm`
- `ge_iff_simplex_ge`
- `le_iff_simplex_le`

The hard theorem-to-theorem edges retained by the source-text countergraph now match the same helper set.

## Findings

- Required and present:
  - `exists_xx_lam0`
  - `exists_yy_mu0`
  - `wsum_wsum_comm`
  - `ge_iff_simplex_ge`
  - `le_iff_simplex_le`

## Decision

The audit is **accepted**.

Reason:
- the mandatory theorem-local dependency set is now present and no extra theorem-adjacent helpers remain in the extracted dependency list after comment stripping and accessor normalization.

## Implication

The source-text dependency extractor now recovers the requested theorem-local helper lemmas for `lam0_le_mu0` without pulling in adjacent proof comments.
