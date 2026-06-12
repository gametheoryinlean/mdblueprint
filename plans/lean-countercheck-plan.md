# Lean Countercheck Plan

## Findings

- Core `mdblueprint-` skills remain Markdown-first.
- `nodes/`, `staged/`, and `mdblueprint.yml` are the human-authored source of truth.
- Lean artifacts are counterchecks against the authored blueprint, not a source of truth.
- The add-on should compare extracted Lean theorems against authored nodes, with optional natural-language hints from `nodes/` or `staged/` for mapping.
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

### Heuristic Lean countercheck pipeline

- `mdblueprint-lean-run-full`
- `mdblueprint-lean-theorem-extraction`
- `mdblueprint-lean-dependency-extraction`
- `mdblueprint-lean-node-generation`
- `mdblueprint-lean-blueprint-export`
- `mdblueprint-lean-countercheck`

### Legacy fallback

- `mdblueprint-lean-theorem-extraction-legacy`

## Primary `mdblueprint-lean-` Skills

- `mdblueprint-lean-run-full`
- `mdblueprint-lean-theorem-extraction`
- `mdblueprint-lean-dependency-extraction`
- `mdblueprint-lean-node-generation`
- `mdblueprint-lean-blueprint-export`
- `mdblueprint-lean-countercheck`

## Input Massaging From Monolithic Lean Files

- read Lean source text directly
- detect theorem, lemma, proposition, and example names conservatively
- extract proof-local theorem dependencies from proof text
- validate the discovery pass on a small sample before batch extraction
- map extracted theorems back to authored nodes using node/staged hints when available
- compare authored dependency DAGs against the Lean-derived countergraph

## Artifact Flow

1. Lean source text
2. theorem-name extraction
3. theorem dependency extraction
4. node-to-theorem mapping
5. countercheck against `nodes/`, `staged/`, and `mdblueprint.yml`
6. warning and drift reporting

## Validation Rule

- regex may be used only as a bootstrap and must be validated on a sample
- natural-language parsing is allowed only as a mapping hint, not as the sole authority
- no direct overwrite of upstream authored files from the add-on
- blank or flawed proofs are not errors if they reflect intentional incompleteness

## Adjudication Layer

- The theorem/dependency extractor is factual in the sense that it reports what the source text exposes, but it is still heuristic and can over- or under-approximate.
- The authored node graph remains the contract boundary.
- The final judge classifies each mismatch as:
  - true discrepancy
  - false abend
  - needs review
- The final filter must be autonomous and case-by-case; it may not blindly inherit the raw Lean graph as authoritative.
- Lean-backed artifacts that are finer-grained than the authored node are not automatically errors.
- Lean-backed artifacts that are weaker than the authored node are incompleteness signals and should be surfaced explicitly.
- `sorry`, stub, or comment leakage should be flagged as provenance noise, not treated as semantic drift unless it changes the authored meaning.

## Smoke Test Findings

- The extraction wrapper must build the target Lean module before import.
- The extractor must filter by the imported target module index, not the wrapper script module.
- Smoke test on a two-theorem Lean file produced:
  - 2 theorem records: `foo`, `bar`
  - 1 hard dependency edge: `bar -> foo`
  - 2 staged node drafts

## Agenda Checklist

- [x] Add a counterchecker skill for comparing Lean-derived graphs against authored nodes and `mdblueprint.yml`
- [x] Keep the heuristic extraction path as the active baseline
- [x] Add a self-contained full-run skill that can reproduce the heuristic pipeline without Lean-first or MCP dependencies
  - [x] Make the skill repository-contained and reproducible from a fresh checkout using an explicit `ECONCSLIB_ROOT` input
- [x] Write and follow a concrete testing plan for source-text theorem/dependency extraction
  - [x] Choose a small Lean sample set for side-by-side extraction
  - [x] Define value-add metrics: setup friction, theorem recall, dependency recall, mapping ambiguity, and false positives
  - [x] Document the setup steps for the heuristic extractor before the experiment
  - [x] Review the repository to decide where the heuristic extractor adds value over a purely heuristic-only baseline
- [x] Use `/nodes`, `/staged`, and `mdblueprint.yml` as the source of truth for mapping and validation
- [x] Allow natural-language hints from `nodes/` or `staged/` when a single node maps to multiple Lean theorems
- [x] Generate a Lean-derived DAG from monoliths without requiring compilation or Lake setup
- [x] Compare the Lean-derived DAG against the ground-truth `blueprint` graph and record drift
  - [x] Build a node-to-theorem crosswalk from authored EconCSLib nodes/staged docs to theorem records
- [x] Flag new lemmata introduced by autoformalisation as interesting proposals, not errors
- [x] Treat blank or flawed proofs as incompleteness, not inconsistency
- [x] Audit `lam0_le_mu0` for the expected theorem-local dependencies:
  - [x] Recorded audit results in `plans/lam0_le_mu0-audit.md`
  - [x] `exists_xx_lam0`
  - [x] `exists_yy_mu0`
  - [x] `ge_iff_simplex_ge`
  - [x] `le_iff_simplex_le`
  - [x] `wsum_wsum_comm`
- [x] Record any instruction drift or dependency-shape mismatches

- [x] Diagnose remaining full-run failure modes from a fresh source-text-only full run
- [x] Diagnose remaining full-run failure modes from a fresh source-text-only full run
- [x] Build the dedicated Lean-vs-authored adjudicator skill with a subagent scaffold
- [x] Align the SkillOpt EconCSLib judge rubric with true discrepancy vs false abend classification

- [x] Implement a dedicated SkillOpt adjudication mode for EconCSLib
