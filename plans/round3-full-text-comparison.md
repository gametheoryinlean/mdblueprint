# Round3 Full Run Comparison

## Correction

The previous comparison note used the wrong local reference. The authoritative source-of-truth node set is in [`gametheoryinlean/EconCSLib`](https://github.com/gametheoryinlean/EconCSLib), and the authoritative resultant graph is in [`gametheoryinlean/blueprint`](https://github.com/gametheoryinlean/blueprint).

The `round3-full-text` run is a theorem-level heuristic graph extracted from Lean source text. It is not a direct node-id equivalent of the authored blueprint graph.

## Authoritative Repositories

- Source of truth nodes and edges: [`gametheoryinlean/EconCSLib`](https://github.com/gametheoryinlean/EconCSLib)
- Resultant published graph: [`gametheoryinlean/blueprint`](https://github.com/gametheoryinlean/blueprint)

## Verified Local Counts

- EconCSLib authored node inventory: `535` nodes
- Blueprint published graph: `535` nodes, `840` edges
- Round3 theorem graph: `1,464` nodes, `2,959` edges

## Overlap

- Direct node-id overlap between round3 and blueprint: `0`
- Direct edge overlap between round3 and blueprint: `0`
- EconCSLib authored node ids and blueprint node ids match exactly in the local clone available here.

## Interpretation

- The round3 run succeeded as a source-text-only extraction baseline.
- The produced graph is much broader and represents theorem extraction from Lean source, not the curated blueprint node graph.
- The correct next step is to map theorem-level output back onto the authored EconCSLib node inventory before judging alignment against the published blueprint graph.

## Files Of Interest

- [`runs/round3-full-text/summary.json`](../runs/round3-full-text/summary.json)
- [`runs/round3-full-text/site/graph.json`](../runs/round3-full-text/site/graph.json)
- [`runs/round3-full-text/knowledge/mdblueprint.yml`](../runs/round3-full-text/knowledge/mdblueprint.yml)
