# Round3 Node-Theorem Crosswalk

## Purpose

This note maps the authored EconCSLib knowledge base to the theorem-level
output from the round3 source-text-only extraction run.

The comparison uses the authored repository as the source of truth:

- [`/home/azureuser/EconCSLib/docs/knowledge/nodes`](file:///home/azureuser/EconCSLib/docs/knowledge/nodes)
- [`/home/azureuser/EconCSLib/docs/knowledge/staged`](file:///home/azureuser/EconCSLib/docs/knowledge/staged)
- [`/home/azureuser/EconCSLib/docs/knowledge/mdblueprint.yml`](file:///home/azureuser/EconCSLib/docs/knowledge/mdblueprint.yml)

The extracted theorem corpus comes from:

- [`/home/azureuser/mdblueprint-clean/runs/round3-full-text/theorems.json`](file:///home/azureuser/mdblueprint-clean/runs/round3-full-text/theorems.json)

The published graph reference is:

- [`/home/azureuser/blueprint-published/graph.json`](file:///home/azureuser/blueprint-published/graph.json)

## Matching Rule

The crosswalk uses a conservative name matcher aligned with the repository
countercheck logic:

- direct string equality
- normalized equality, where names are lowercased and stripped of
  non-alphanumeric characters
- basename fallback, so `Foo.bar` can match `bar` when the basename is the
  meaningful theorem name

Candidate authored labels for each EconCSLib node include:

- `id`
- `title`
- file stem
- `lean.declarations`
- declaration basenames

This intentionally treats node-to-theorem mapping as many-to-one:

- a single authored node may map to multiple Lean theorem records
- a theorem record maps to at most one authored node in the report summary

## Inventory

- authored EconCSLib docs in `nodes/` and `staged/`: `535`
- authored docs with `lean.declarations`: `322`
- theorem records extracted from the round3 Lean-source run: `1,590`

## Crosswalk Summary

- authored nodes matched to at least one theorem record: `249`
- theorem records matched to authored nodes: `719`
- theorem records left unmapped: `871`
- maximum theorem records attached to a single authored node: `42`

## Nodes With Many Theorems

These authored nodes split into many theorem records in the source-text run.
That is expected when a single human-authored concept expands into a cluster of
helper lemmas or formalization scaffolding.

- `social_choice.fair_division.cardinal_instance_wrappers` -> `42` theorem records
- `mechanism_design.bayesian.bayesian_mechanisms` -> `21`
- `game_theory.strategic_game.core.mixed_strategy` -> `16`
- `game_theory.extensive_game.equilibrium.reached_subgame_nash_restriction` -> `15`
- `game_theory.strategic_game.zero_sum.lam_mu_existence` -> `15`
- `game_theory.strategic_game.zero_sum.core.optimal_strategy_sets_are_polytopes` -> `14`
- `math.simplex.mix` -> `12`
- `math.linear_algebra.theorem_of_alternative.fourier_motzkin` -> `11`
- `foundation.preference.strictly_preferred` -> `10`
- `mechanism_design.auction.bayesian.single_item_framework` -> `10`
- `mechanism_design.auction.basic.ordered_bid_utilities` -> `9`
- `mechanism_design.auction.basic.reserve_second_price_dsic` -> `9`

## Unmapped Theorem Clusters

The unmapped theorem records are the clearest evidence that the formalisation
process introduced additional theorem-level artifacts that are not present as
authored EconCSLib nodes.

The largest unmapped source modules are:

- `EconCSLib.MechanismDesign.Auction.OptimalSingleItem` -> `148` unmapped theorem records
- `EconCSLib.MechanismDesign.Auction.BayesianSingleItem` -> `79`
- `EconCSLib.Math.FixedPoint.Scarf` -> `60`
- `EconCSLib.MechanismDesign.Auction.Knapsack` -> `30`
- `EconCSLib.MarketDesign.Matching.GaleShapley` -> `28`
- `EconCSLib.GameTheory.ExtensiveGame.BehaviorStrategy` -> `25`
- `EconCSLib.MarketDesign.Matching.Lattice` -> `25`
- `EconCSLib.SocialChoice.Voting.Basic` -> `23`
- `EconCSLib.Math.FixedPoint.Brouwer` -> `21`
- `EconCSLib.Math.FixedPoint.Brouwer_product` -> `20`
- `EconCSLib.Examples.CentipedeGame` -> `17`
- `EconCSLib.SocialChoice.Voting.VotingRules` -> `17`
- `EconCSLib.Examples.TicTacToe` -> `16`
- `EconCSLib.GameTheory.ExtensiveGame.Zermelo` -> `16`
- `EconCSLib.Examples.CandidateChoice` -> `13`
- `EconCSLib.OpenProblem.SubmodularWelfareDemandOracle` -> `13`
- `EconCSLib.GameTheory.ExtensiveGame.GameTreeNE` -> `9`
- `EconCSLib.GameTheory.ExtensiveGame.Subgame` -> `9`
- `EconCSLib.GameTheory.ExtensiveGame.BackwardInduction` -> `8`
- `EconCSLib.GameTheory.ExtensiveGame.FiniteArenaExtraction` -> `8`

Representative extra theorem names include:

- `payoff`, `terminal`, `majorityOutcome_*`, `candidateChoice_*`
- `centipede*`, `cp3`, `mover`, `next`
- `rps_*`, `uniform`, `uniformProfile`
- `Vickrey`, `truthful_weakly_dominant_p0`, `truthful_weakly_dominant_p1`
- `sample_zermelo_determinacy`, `leaf_hasOnlyRootSubgames`
- `diagonalGame*`, `matchingPennies_*`, `threeByTwo_*`

## Interpretation

The round3 extraction is broader than the authored knowledge base in two ways:

1. It expands authored nodes into multiple theorem records.
2. It introduces theorem records that have no direct authored node analogue.

That means the theorem graph is useful as a countercheck and as a source of
candidate additional formalisation nodes, but it should not be treated as a
replacement for the authored EconCSLib inventory.

At the graph level:

- authored EconCSLib nodes/staged docs: `535`
- round3 theorem graph nodes: `1,464`

So the formalisation-derived graph contains `929` additional graph nodes beyond
the authored inventory.

## Follow-Up

- Use this crosswalk to project theorem-level output back onto authored node ids.
- Compare the projected subgraph against the published blueprint graph.
- Treat unmatched theorem records as candidate new lemmas or helper artifacts,
  not as inconsistencies.



## Edge-Level Comparison Against Blueprint

The theorem-level dependency graph was projected back onto authored EconCSLib
node ids by mapping theorem records to authored nodes and then lifting theorem
edges into node edges.

- projected node set size: `254`
- blueprint node set size: `535`
- projected edges: `963`
- blueprint edges: `840`
- overlapping edges: `154`
- projected-only edges: `809`
- blueprint-only edges: `686`
- edge precision vs blueprint: `0.1599`
- edge recall vs blueprint: `0.1833`

Interpretation:

- the projection recovers a small aligned subgraph, but most theorem-level edges
  are not present in the authored blueprint graph
- many projected-only edges connect theorem clusters that are useful for
  formalization review, but are outside the curated blueprint edge set
- many blueprint-only edges correspond to authored node relationships that the
  round3 source-text heuristic did not recover

Examples of projected-only edges include:

- `foundation.preference.indifferent -> math.minimax.loomis_induction_proof.base_case`
- `foundation.preference.strictly_preferred -> math.minimax.loomis_induction_proof.weak_duality`
- `game_theory.extensive_game.core.game_tree -> game_theory.extensive_game.perfect_information.backward_induction_value`
- `mechanism_design.auction.basic.reserve_second_price_dsic -> mechanism_design.basic.dsic_predicate`

Examples of blueprint-only edges include:

- `foundation.cost.costm -> foundation.cost.cells`
- `foundation.preference.strictly_preferred -> foundation.preference.represents_preference`
- `foundation.preference.total_preorder -> foundation.argmax.list_arg_max_on`
- `game_theory.cooperative_game.shapley_value -> game_theory.cooperative_game.shapley_uniqueness`
- `game_theory.extensive_game.core.game_tree -> game_theory.extensive_game.core.history_and_subgame`

