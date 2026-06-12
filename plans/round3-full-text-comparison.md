# Round3 Full Run Comparison

## Run Summary

- Input source root: `/home/azureuser/EconCSLib`
- Output directory: `/home/azureuser/mdblueprint-clean/runs/round3-full-text`
- Lean files processed: `143`
- Theorem records extracted: `1,590`
- Dependency edges extracted: `6,130`
- Published site graph nodes: `1,455`
- Published site graph edges: `2,959`

## Ground Truth Reference

Compared against the locally available blueprint export at `/home/azureuser/econcslib-blueprint-full-export`.
This repo contains the authored `nodes/`, `staged/`, and `mdblueprint.yml` source of truth.

## Comparison Notes

- Direct node-id overlap between the round3 graph and the authored blueprint graph: `0`
- Title-level overlap after conservative normalization: `13`
- Shared normalized titles include:
  - `allocation`
  - `condorcetwinner`
  - `faircutpointexists`
  - `farkaslemma`
  - `lottery`
  - `matchingpennies`
  - `measurevaluation`
  - `mixednashequilibrium`
  - `mixedstrategy`
  - `payoffvector`
  - `strategyprofile`
  - `strategyproofmonotonic`
  - `surethingprinciple`

## Interpretation

- The source-text-only round3 run successfully extracted a large theorem/dependency graph without Lean.
- The output is much broader than the authored blueprint and is not yet semantically aligned with the blueprint node inventory.
- The mismatch is expected at this stage because the extractor is heuristic and works from Lean source text, while the blueprint repo is a curated authored source of truth.
- The graph now exists as a reproducible baseline that future counterchecks can refine toward the authored blueprint.

## Files Of Interest

- [`runs/round3-full-text/summary.json`](../runs/round3-full-text/summary.json)
- [`runs/round3-full-text/site/graph.json`](../runs/round3-full-text/site/graph.json)
- [`runs/round3-full-text/knowledge/mdblueprint.yml`](../runs/round3-full-text/knowledge/mdblueprint.yml)
