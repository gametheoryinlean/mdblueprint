# Lean Countercheck Plan

## Findings

- Core `mdblueprint-` skills remain Markdown-first.
- `nodes/`, `staged/`, and `mdblueprint.yml` are the human-authored source of truth.
- Lean artifacts are counterchecks against the authored blueprint, not a source of truth.
- The add-on should compare extracted Lean theorems against authored nodes, with optional natural-language hints from `nodes/` or `staged/` for mapping.
- `lean-lsp-mcp` is an alternative extraction path; pure LLM extraction remains another fallback.
- Proofs may be blank or flawed without implying inconsistency, as long as the authored node is intentionally incomplete.
- The counterchecker should surface warnings, drift, and newly introduced lemmata, but not overwrite authored `mdblueprint.yml` or `docs/`.

## Contract Scope

### Core mdblueprint pipeline

- `mdblueprint-source-extraction`
- `mdblueprint-source-proof-recovery`
- `mdblueprint-node-author`
- `mdblueprint-node-review`
- `mdblueprint-lean-generation`
- `mdblueprint-lean-linking`
- `mdblueprint-alignment-review`
- `mdblueprint-publish`

### Lean countercheck pipeline

- `mdblueprint-lean-theorem-extraction`
- `mdblueprint-lean-dependency-extraction`
- `mdblueprint-lean-node-generation`
- `mdblueprint-lean-blueprint-export`
- `mdblueprint-lean-countercheck`

### Legacy fallback

- `mdblueprint-lean-theorem-extraction-legacy`

## Primary `mdblueprint-lean-` Skills

- `mdblueprint-lean-theorem-extraction`
- `mdblueprint-lean-dependency-extraction`
- `mdblueprint-lean-node-generation`
- `mdblueprint-lean-blueprint-export`
- `mdblueprint-lean-countercheck`

## Input Massaging From Monolithic Lean Files

- read Lean source text directly or via `lean-lsp-mcp`
- detect theorem, lemma, proposition, and example names conservatively
- extract proof-local theorem dependencies from proof text
- validate the discovery pass on a small sample before batch extraction
- map extracted theorems back to authored nodes using node/staged hints when available
- compare authored dependency DAGs against the Lean-derived countergraph

## Artifact Flow

1. Lean source text or `lean-lsp-mcp` output
2. theorem-name extraction
3. theorem dependency extraction
4. node-to-theorem mapping
5. countercheck against `nodes/`, `staged/`, and `mdblueprint.yml`
6. warning and drift reporting

## Validation Rule

- regex may be used only as a bootstrap and must be validated on a sample
- natural-language parsing is allowed only as a mapping hint, not as the sole authority
- no direct overwrite of upstream authored files from the add-on
- Lean compilation and Lake environment setup are optional and not required for the countercheck
- blank or flawed proofs are not errors if they reflect intentional incompleteness

## Smoke Test Findings

- The extraction wrapper must build the target Lean module before import.
- The extractor must filter by the imported target module index, not the wrapper script module.
- Smoke test on a two-theorem Lean file produced:
  - 2 theorem records: `foo`, `bar`
  - 1 hard dependency edge: `bar -> foo`
  - 2 staged node drafts

## Experiment Plan

- Compare `lean-lsp-mcp` and pure LLM extraction on a small sample set.
- Measure theorem-name recall, dependency recall, mapping ambiguity, setup friction, and obvious false positives.
- Review the repository to document the value-add of `lean-lsp-mcp` over a heuristic LLM-only extractor.
- Keep the results as a countercheck report and experiment notes, not as authored-file updates.

## Setup Plan for `lean-lsp-mcp`

- Install `uv` if it is not already present.
- Run `lake build` in the Lean project before starting the MCP server so the language-server path is warm.
- Start `lean-lsp-mcp` with `uvx lean-lsp-mcp`, or use the repo's Nix package if that is the local convention.
- For Claude Code, add the server from the Lean project root with `claude mcp add lean-lsp uvx lean-lsp-mcp`.
- Install `ripgrep` (`rg`) if local search support is needed.
- Do not assume the server is already installed; verify availability as part of the experiment.

## Agenda Checklist

- [x] Add a counterchecker skill for comparing Lean-derived graphs against authored nodes and `mdblueprint.yml`
- [ ] Evaluate `lean-lsp-mcp` as an alternative to pure LLM theorem/dependency extraction (deprioritized)
- [x] Keep pure LLM extraction as a fallback and compare its failure modes against `lean-lsp-mcp`
- [ ] Write and follow a concrete testing plan for `lean-lsp-mcp` vs pure LLM extraction (paused)
  - [x] Choose a small Lean sample set for side-by-side extraction
  - [x] Define value-add metrics: setup friction, theorem recall, dependency recall, mapping ambiguity, and false positives
  - [ ] Document the setup steps for `lean-lsp-mcp` before the experiment (paused)
  - [ ] Review the repository to decide where `lean-lsp-mcp` adds value over heuristic extraction (paused)
- [x] Use `/nodes`, `/staged`, and `mdblueprint.yml` as the source of truth for mapping and validation
- [x] Allow natural-language hints from `nodes/` or `staged/` when a single node maps to multiple Lean theorems
- [x] Generate a Lean-derived DAG from monoliths without requiring compilation or Lake setup
- [ ] Compare the Lean-derived DAG against the ground-truth `blueprint` graph and record drift
- [x] Flag new lemmata introduced by autoformalisation as interesting proposals, not errors
- [x] Treat blank or flawed proofs as incompleteness, not inconsistency
- [ ] Audit `lam0_le_mu0` for the expected theorem-local dependencies:
  - [ ] `exists_xx_lam0`
  - [ ] `exists_yy_mu0`
  - [ ] optionally `ge_iff_simplex_ge`, `le_iff_simplex_le`, `wsum_wsum_comm`
- [ ] Record any instruction drift or dependency-shape mismatches
