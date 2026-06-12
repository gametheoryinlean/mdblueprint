---
name: mdblueprint-lean-countercheck
description: Use when comparing Lean-derived theorem graphs against authored nodes, staged drafts, and mdblueprint.yml, using lean-lsp-mcp, source-text extraction, or pure LLM extraction as alternative inputs.
---

# mdblueprint-lean-countercheck

Countercheck Lean-derived theorem graphs against the authored mdblueprint
sources of truth: `nodes/`, `staged/`, and `mdblueprint.yml`.

This skill is a validator and proposal surface, not an authoring surface.

## When to use

Use this skill when you need to:

- compare extracted Lean theorems against their corresponding authored nodes
- check whether proof-local dependencies drifted from the authored DAG
- detect new lemmata introduced by autoformalisation
- compare extraction methods (`lean-lsp-mcp` vs pure LLM extraction)
- sanity-check a DAG generated from Lean monoliths against the ground truth

## Inputs

- authored node(s) from `nodes/` or `staged/`
- `mdblueprint.yml`
- optional natural-language hints from node text or staged drafts
- Lean-derived theorem names and dependency edges from any extraction method

## Supported extraction methods

- `lean-lsp-mcp` for Lean-aware structured extraction when available
- pure LLM-based extraction when `lean-lsp-mcp` is unavailable or brittle
- source-text extraction as a fallback for quick probes

## `lean-lsp-mcp` setup

If `lean-lsp-mcp` is not already installed, set it up explicitly before
experimenting:

1. Install `uv` on the machine.
2. Run `lake build` in the target Lean project before starting the MCP server so the language-server path is warm.
3. Start `lean-lsp-mcp` with `uvx lean-lsp-mcp`, or use the repo's Nix package if that is the local convention.
4. For Claude Code, add the server from the Lean project root with `claude mcp add lean-lsp uvx lean-lsp-mcp`.
5. Install `ripgrep` (`rg`) if local search support is needed.

Do not assume the server is already installed; verify availability as part of the experiment.

## Experiment plan

- Run the same small sample through `lean-lsp-mcp` and a pure LLM extractor.
- Compare theorem-name recall, dependency recall, ambiguous mappings, and setup friction.
- Review the repository to document the value-add of `lean-lsp-mcp` over a heuristic LLM-only approach.
- Keep the result as a countercheck report and experiment notes, not as authored-file updates.

## Core rules

- Treat `nodes/`, `staged/`, and `mdblueprint.yml` as authoritative.
- Treat Lean as a counterchecker, not the source of truth.
- Do not require compilation or a Lake environment for the countercheck.
- Do not overwrite `mdblueprint.yml` or `docs/`.
- Do not raise errors for blank or flawed proofs if the issue is incompleteness rather than inconsistency.
- Use natural-language hints from node text only to help map one node to multiple Lean theorems.
- Record new lemmata introduced by autoformalisation as proposals or warnings.
- Check DAG-ification constraints, but remember they are enforced upstream.

## Workflow

1. Build or ingest Lean-derived theorem names and dependencies.
2. Map extracted theorems back to authored nodes.
3. Compare the Lean-derived graph to the authored dependency graph.
4. Flag drift, missing edges, suspicious new lemmata, and mapping ambiguity.
5. Compare alternative extraction methods and keep the strongest countercheck result.
6. Report warnings and proposals only; do not patch authored files.

## Outputs

- theorem-to-node mapping proposals
- drift warnings
- dependency mismatch warnings
- new-lemma proposals
- method comparison notes for `lean-lsp-mcp` vs pure LLM extraction
- ground-truth comparison notes for DAG shape

## Non-goals

- Do not treat lack of Lean provenance as an error.
- Do not prove correctness of the entire repository.
- Do not make authored content secondary to Lean output.
- Do not force a compile step just to produce the countercheck.
