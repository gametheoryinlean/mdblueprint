# Blueprint Lint Implementation Plan

> **Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).
> The issue is the canonical design source; this file stages the work into
> reviewable PRs. If the design changes, update both.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan PR-by-PR. Each PR
> uses checkbox (`- [ ]`) tasks; tick them as you complete them.

**Goal:** Add `mdblueprint-lint`, a single Python orchestrator that surfaces
duplicate, structural, and reference issues across the knowledge base. The
orchestrator may dispatch judgement-heavy checks to a Claude subagent through
an injected runner, but all detectors share one diagnostic pipeline,
configuration, and cache.

**Non-goals (this plan):** embedding-family detectors, auto-fix, HTML
overlays, new in-prose reference syntax, hot-spot dashboards.

All paths below are relative to `/Users/hoxide/mycodes/mdblueprint`.

---

## Current State

- `tools/knowledge/check.py` is the strict publish gate: schema, topic
  registry, ID uniqueness, DAG cycles. It must stay short and hard.
- `tools/knowledge/validator.Diagnostic` has only `level ∈ {"error",
  "warning"}` and lacks a stable rule code.
- `tools/knowledge/graph.py` builds `KnowledgeGraph` and detects cycles —
  reuse for structural detectors.
- `tools/knowledge/proof_fill.py:43` defines `CodexRunner = Callable[[str],
  str]` and `_make_claude_cli_runner` wraps `subprocess.run(["claude",
  "-p", ...])`. Lint reuses the same shape for `LlmRunner`.
- `docs/knowledge/` currently has 1 admitted node and 1 staged node; small
  fixture sets are fine for tests.

## Architecture Recap

See issue #121 for the full design. Summary:

```python
LlmRunner = Callable[[str], str]

class Detector(Protocol):
    code: str
    needs_llm: bool
    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]: ...
```

- One `Linter` orchestrator owns load / build-graph / run-detectors /
  render.
- Detectors are deterministic or LLM-backed; same protocol either way.
- LLM detectors require an injected `LlmRunner`; tests pass a fake.
- LLM detectors are deterministic across reruns via a JSON cache.

## Detector Inventory (in scope)

| # | Detector | Family | Severity | Rule code |
| --- | --- | --- | --- | --- |
| 1 | Title / statement fuzzy duplicate | Deterministic | warning | `LINT_FUZZY_DUP` |
| 2 | Staged ↔ admitted overlap | Deterministic | warning | `LINT_STAGED_OVERLAP` |
| 3 | Redundant dependency edge | Deterministic | info | `LINT_REDUNDANT_DEP` |
| 4 | Orphan node | Deterministic | info | `LINT_ORPHAN` |
| 6 | Lean ref kind mismatch | Deterministic | warning | `LINT_LEAN_KIND` |
| 9 | Semantic duplicate (pairwise) | LLM | warning | `LINT_SEMANTIC_DUP` |
| 10 | Statement ↔ Lean alignment | LLM | warning | `LINT_LEAN_ALIGN` |

Deferred: 5 (prose ↔ deps), 7 (alias hygiene extension), 8 (hot spots),
embedding family.

---

## Staged PR Plan

Each PR is independently mergeable. PR 1 → 2 is the critical path. PRs 3,
4, 5 are parallelizable once 2 lands. PRs 6 → 7 form the LLM track.

### PR 1 — Diagnostic data-model extension

**Scope:** Infrastructure only. Zero behaviour change for `check`.

- [ ] `tools/knowledge/validator.py`: `Diagnostic` gains
      `code: str | None = None` and `related: tuple[str, ...] = ()`;
      `level` accepts `"info"`. Update `__str__` to include `code`
      when set.
- [ ] New `tests/test_diagnostic.py` covering all level / code / related
      combinations and `__str__` formatting.
- [ ] Full suite green: `uv run --extra dev python -m pytest -q`.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` output
      unchanged (visual diff).

**Done when:** all existing tests pass; new test passes; no consumer of
`Diagnostic` needs changes.

### PR 2 — Lint orchestrator skeleton + CLI

**Scope:** Stand up `mdblueprint-lint` with the `Detector` protocol and
a no-op detector list. No real detectors yet.

- [ ] New `tools/knowledge/lint.py` (~200 lines target):
  - `LlmRunner = Callable[[str], str]`.
  - `Detector` protocol with `code`, `needs_llm`, `run(...)`.
  - `class Linter`: loads nodes via `parser.scan_directory`, builds
    graph via `graph.build_graph`, calls each detector, returns
    `list[Diagnostic]`.
  - `render_text(diags)` grouped by detector code.
  - `render_json(diags)` machine-readable.
  - `main(argv)` with flags: `--no-llm` (default), `--llm`,
    `--llm-budget N` (default 50), `--model`, `--cache-dir`
    (default `.mdblueprint/lint-cache/`), `--no-cache`, `--json`,
    `--strict-warnings`.
  - `_make_claude_cli_runner(model)` — copy the shape of
    `proof_fill._make_claude_cli_runner`. No abstraction extraction yet.
- [ ] `pyproject.toml`: register
      `mdblueprint-lint = "tools.knowledge.lint:main"`.
- [ ] New `tests/test_lint_orchestrator.py`:
  - Inject a fake detector that returns `[]` → assert exit 0 and
    "no findings" output.
  - Inject a fake detector that returns one warning → assert grouped
    text contains `code`; assert `--json` parses; assert
    `--strict-warnings` exits non-zero.
  - Assert LLM-needing detector is skipped when `--no-llm`.

**Done when:** `uv run mdblueprint-lint docs/knowledge` exits 0 with 0
findings; new file < 250 lines.

### PR 3 — Detectors 1 + 2 (fuzzy title/statement, staged ↔ admitted)

- [ ] In `tools/knowledge/lint.py` (or a sub-module if it pushes past
      ~400 lines): `_normalize(text)` — lowercase, collapse whitespace,
      strip leading/trailing punctuation. `_ratio(a, b)` via
      `difflib.SequenceMatcher` (stdlib — no rapidfuzz dep).
- [ ] `FuzzyTitleDupDetector` (code `LINT_FUZZY_DUP`): scans all admitted
      pairs; emits warning when ratio ≥ threshold; `related` holds the
      other node id.
- [ ] `StagedAdmittedOverlapDetector` (code `LINT_STAGED_OVERLAP`): same
      ratio function, restricted to (staged × admitted) pair set.
- [ ] Threshold: default 0.92, configurable via
      `mdblueprint.yml → lint.fuzzy_threshold`. Update `config.py`
      schema accordingly.
- [ ] Tests in `tests/test_lint_fuzzy.py`:
  - Trigger: punctuation/case/whitespace variants.
  - Non-trigger: unrelated titles.
  - staged↔admitted: pair set restriction verified.

**Done when:** example knowledge base produces zero false positives at
default threshold.

### PR 4 — Detectors 3 + 4 (redundant deps, orphans)

- [ ] `RedundantDepDetector` (code `LINT_REDUNDANT_DEP`): for each edge
      `u→v`, BFS from `u` over edges other than `u→v`; if `v` reachable,
      report info; `related = (v,)`.
- [ ] `OrphanDetector` (code `LINT_ORPHAN`): emits info for each node
      with `in_degree == 0 and out_degree == 0`. No exception list this
      PR — issue Open Question #1 tracks the design.
- [ ] Tests in `tests/test_lint_structure.py`:
  - Chain `A→B→C` plus extra `A→C` → expect `LINT_REDUNDANT_DEP` on
    `A→C` only.
  - Acyclic graph with no redundancy → 0 findings.
  - Isolated node → one `LINT_ORPHAN`.

**Done when:** example base runs cleanly; structural tests deterministic.

### PR 5 — Detector 6 (Lean ref kind mismatch)

- [ ] `LeanRefKindDetector` (code `LINT_LEAN_KIND`): walk each node's
      `lean_refs`; resolve against a `LeanIndex` built via
      `tools.knowledge.lean_index.index_lean_project(lean_root)` (lookup
      by fully qualified name); compare `LeanDeclaration` kind vs node
      `statement.kind`; mismatch → warning; missing Lean root (no
      configured repository on disk) → emit one info `"lean index not
      available; skipping LINT_LEAN_KIND"` and return.
- [ ] Tests in `tests/test_lint_lean_kind.py`:
  - Inject fake `lean_index` dict.
  - Trigger: `kind=theorem` vs lean `def`.
  - Non-trigger: matching kinds.
  - No index: detector emits info, no warnings.

**Done when:** with the bundled example (no Lean refs), detector is a
no-op; with fixture-injected refs, mismatches are reported.

### PR 6 — LLM runner + cache + Detector 9 (semantic duplicate pairwise)

- [ ] `lint.py`: implement `_LintCache` — JSON file per detector under
      `--cache-dir`; key `(detector_code, sorted_ids, content_hash)`;
      atomic write.
- [ ] `SemanticDupDetector` (code `LINT_SEMANTIC_DUP`, `needs_llm=True`):
  - Builds candidate pair set by **rerunning the fuzzy ratio at a
    lower threshold** (default 0.75, configurable via
    `mdblueprint.yml → lint.semantic_candidate_threshold`), then
    taking the top-N pairs by ratio capped at `--llm-budget`.
    Rationale: keeps the detector self-contained and avoids coupling
    to upstream diagnostic plumbing.
  - Prompt per pair: node ids + titles + statements + ask for JSON
    `{"same": bool, "reason": str}`. Include a `_PROMPT_VERSION = 1`
    constant in the hash input so prompt edits invalidate cache.
  - Parses response defensively (JSON decode error → skip pair, emit
    one info diagnostic with the raw snippet truncated to 200 chars).
  - `same: true` → warning, `related = (other_id,)`.
- [ ] Cap by `--llm-budget`; abort cleanly with info message when hit.
- [ ] Tests in `tests/test_lint_llm_semantic.py`:
  - Fake `LlmRunner` captures the prompt; assert it contains both
    statements and an instruction to return JSON.
  - Fake runner returns `'{"same": true, "reason": "..."}'` →
    expect one warning with `related`.
  - Second run with same inputs and a counter-wrapped runner →
    expect zero calls (cache hit).
  - `--llm-budget 0` → zero calls, info diagnostic about budget.

**Done when:** Fake-runner suite green; CI does not call real
`claude` binary; cache file written and reused.

### PR 7 — Detector 10 (statement ↔ Lean alignment)

- [ ] `LeanAlignmentLlmDetector` (code `LINT_LEAN_ALIGN`,
      `needs_llm=True`):
  - For each node with `lean_refs`, call
    `tools.knowledge.lean_alignment.build_alignment_bundle(
    knowledge_root, node.id, declaration)` to obtain the bundle of
    statement + Lean source + metadata used elsewhere in the project.
  - Prompt: bundle fields + ask for JSON
    `{"aligned": bool, "reason": str}`. Include
    `_PROMPT_VERSION = 1` in the cache hash input.
  - `aligned: false` → warning, `related = (lean_ref_id,)`.
  - Cache key includes `sha256(bundle_json)` so any bundle change
    invalidates.
- [ ] Tests in `tests/test_lint_llm_lean_align.py` mirror PR 6 pattern.

**Done when:** Fake-runner tests green; cache behaviour matches PR 6.

### PR 8 — Documentation + AGENTS.md note

- [ ] New `docs/lint.md`: one section per rule code with what it checks,
      example trigger, how to fix.
- [ ] `AGENTS.md`: add `mdblueprint-lint` to the dev-commands list under
      "Focused checks", with the `--no-llm` default emphasised.
- [ ] `README.md`: one-line link to `docs/lint.md` if a checks/QA section
      already exists.
- [ ] Optional CI wiring is deferred to its own issue.

**Done when:** `mdblueprint-lint --help` text matches the documented
flag set; running each detector against a small fixture produces output
that matches the doc's "example trigger" block.

---

## Risk Notes

- **Threshold tuning (PR 3):** 0.92 is a guess. Track on real
  `docs/knowledge` data once admitted-node count > 5. If FP rate is
  bad, add config knob before adding semantic LLM detector.
- **Prompt drift (PR 6, 7):** LLM detectors must produce parseable JSON.
  Wrap the call in a "parse → on failure, log + skip" path so a flaky
  response cannot crash the run.
- **Cache key stability (PR 6):** `content_hash` must include every
  prompt-affecting field. Bumping the prompt template is a cache-break
  event — add a `_PROMPT_VERSION` constant in the hash input so version
  bumps invalidate cleanly.
- **Module size (PR 2 → 3):** If `lint.py` crosses ~400 lines, split into
  `lint/__init__.py` + `lint/_detectors/*.py` before PR 4 lands.

## Open Questions (tracked in issue #121)

1. Orphan exception mechanism (PR 4 ships without; refine if needed).
2. Per-detector configurability of fuzzy threshold.
3. LLM detectors in CI (off by default; design CI placement separately).
