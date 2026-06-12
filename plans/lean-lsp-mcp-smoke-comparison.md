# lean-lsp-mcp Smoke Comparison

## Goal

Compare the local text-only countercheck path against the MCP-backed Lean path on a small sample node, and record the practical runtime / reliability differences.

## Sample

- node: `strategic_games.weakly_dominant_strategy`
- Lean file: `EconCSLib/GameTheory/StrategicGame/Dominance.lean`

## Measured Baseline

### Text-only heuristic path

Observed run:

- command: `mdblueprint-lean-countercheck --method heuristic`
- wall time: `124.66s`
- result:
  - `missing_uses = []`
  - `extra_uses = ['IsBestResponse', 'IsStrictlyDominant', 'IsWeaklyDominant', 'Profile', 'Strategy', 'StrictlyDominates', 'T2', 'deviate_self', 'le_of_lt', 'le_refl']`
  - matched declaration: `StrategicGame.IsWeaklyDominant`

Interpretation:

- This path finishes, but it is brittle in how it maps authored hints to Lean names.
- It still needs normalization to compare `strategic_games.weakly_dominates` against `WeaklyDominates`.
- The current heuristic filters are suppressing tactic noise and single-letter garbage, which is good, but the path is still text-driven and therefore conservative.

## MCP-Backed Path

Observed run:

- command: `mdblueprint-lean-countercheck --method mcp`
- status during the smoke window: still starting up / not yet finished
- elapsed time observed before troubleshooting: several minutes

Process observations:

- the server was launched via `uvx lean-lsp-mcp --transport stdio --lean-project-path /home/azureuser/EconCSLib`
- multiple stale probe processes were present from earlier experiments, which added background load
- the active MCP process was low CPU and moderate memory, which suggests bootstrap / Lean initialization rather than a tight compute loop
- `iostat` showed only modest disk utilization in the troubleshooting snapshot, so the bottleneck was not a saturated disk at that moment

Interpretation:

- the MCP server is heavier to start than the text-only heuristic baseline
- that overhead is expected because it bootstraps a Lean-aware server, not just a regex pass
- the startup cost is the main practical downside for small one-off smoke checks

## Normalization Requirement

Yes, string normalization is still needed even with an LSP-backed path.

The mapping layer should normalize both authored hints and Lean names by:

- lowercasing
- stripping punctuation / separators
- comparing normalized full names
- comparing normalized basenames as a fallback

Without this, authored hints like `strategic_games.weakly_dominates` will not match Lean names such as `WeaklyDominates` reliably.

## Practical Finding

For this sample:

- the heuristic path is faster to get a result, but it is text-driven and brittle
- the MCP path is more promising for reliability, but the startup cost is materially higher
- normalization is still required in both flows for authored-node-to-Lean-name mapping

## Recommendation

Use `lean-lsp-mcp` where reliability matters and where the project can afford the startup cost.
Keep the text-only heuristic as a fallback and regression baseline, especially for smoke tests and quick iteration.


## Status Update

The MCP-backed path is being removed from the active agenda for now because it depends on a warm Lean project state and a `lake build` step that is too heavy for the current local workflow. The text-only heuristic path remains the practical baseline.
