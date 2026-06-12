---
name: mdblueprint-lean-run-full
description: Use when running the full mdblueprint heuristic pipeline end to end from Lean source text, generating theorem records, dependency edges, staged nodes, and a generated blueprint bundle without Lean-first or MCP-based extraction.
---

# mdblueprint-lean-run-full

Run the full heuristic mdblueprint pipeline from Lean source text.

This skill lives in the `mdblueprint-clean` repository and is intended to be
reproducible from a fresh checkout. It does not depend on Lean installation,
`lake env lean`, Lean-first extraction, `lean-lsp-mcp`, or any MCP-backed
workflow.

## Purpose

- extract theorem-like declarations from Lean source text
- extract proof-local theorem dependencies heuristically
- generate staged node drafts
- materialize a generated `mdblueprint.yml` bundle
- optionally compare the generated graph against a ground-truth blueprint graph

## Inputs

- the repository root of `mdblueprint-clean`
- a checkout of the target Lean repository, for example `EconCSLib`
- an output directory for run artifacts
- optional ground-truth graph path for comparison

## Outputs

- `theorems.json`
- `dependencies.json`
- staged node drafts
- generated blueprint bundle
- `summary.json`
- optional `comparison.json`

## Repository-contained workflow

Run this from the `mdblueprint-clean` repository root.

Set the target Lean repository path explicitly, for example:

```bash
export ECONCSLIB_ROOT=/path/to/EconCSLib
```

Then run from the `mdblueprint-clean` repository root:

```bash
uv run mdblueprint-lean-run-full --project-root "$ECONCSLIB_ROOT" --source-root "$ECONCSLIB_ROOT" --output-dir runs/round3-full-heuristic --skip-build --resume
```

The command above uses only repository-local tooling plus the external source
checkout path you provide. No ad hoc local scripts are required, and no Lean
compiler installation is needed for this path.

## Run order

1. Confirm the output directory does not contain a stale partial run.
2. If the directory exists and you want to keep partial outputs, use `--resume`.
3. Run the heuristic full pipeline through `mdblueprint-lean-run-full`.
4. Publish or inspect the generated `site/` and `knowledge/` outputs.
5. Record any drift, missing edges, or unexpected theorem-name mismatches in a plan note.

## Notes on `nohup`

- `nohup` is only a shell launcher wrapper.
- It detaches the command from the terminal so it can keep running after logout.
- `nohup` is not part of the skill logic and should not be treated as the workflow itself.

## Rules

- Do not use Lean-first extraction in this round3 workflow.
- Do not use `lean-lsp-mcp` or any MCP-backed route here.
- Prefer the heuristic source-text extraction path.
- Keep the run self-contained so another operator can reproduce it from the skill file alone.
- Do not require a local Lean installation or `lake build` for this path.
- If the output directory already exists, prefer `--resume` over deleting the run unless a clean restart is explicitly desired.

## When to inspect the results

- If the run succeeds, inspect `summary.json` first.
- Then inspect `comparison.json` if a ground-truth graph was provided.
- Then review the generated staged nodes and `mdblueprint.yml`.
