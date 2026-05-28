# Multi-Candidate Proofs Implementation Plan

> **Tracking issue:** [#159](https://github.com/gametheoryinlean/mdblueprint/issues/159).
> The issue is the canonical design source; this file stages the work into
> reviewable PRs. If the design changes, update both.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan PR-by-PR. Each PR
> uses checkbox (`- [ ]`) tasks; tick them as you complete them.

**Goal:** Allow a canonical theorem/lemma to host multiple independent proof
candidates in parallel via a subdirectory layout
(`nodes/<topic>/<id>/canonical.md` + `nodes/<topic>/<id>/candidates/cand-X.md`),
while single-file canonicals (`nodes/<topic>/<id>.md`) keep working unchanged.
Promotion picks one candidate as the active proof; abandonment retires a
candidate without deleting its independently-admitted helper lemmas.

**Non-goals (this plan):**

- MCTS or any learned selector for which candidate to work on next.
- Lean alignment changes (Phase IV concerns).
- A long-running daemon to schedule candidate work — everything stays CLI-driven.
- Cross-canonical branching ("what if the definition were different").
- Multi-candidate support in `staged/` (only `nodes/` for now).

All paths below are relative to `/Users/hoxide/mycodes/mdblueprint`.

---

## Current State

- `tools/knowledge/models.py:64` defines `VALID_STATUSES` with 9 values; no
  `candidate`/`promoted`/`abandoned`.
- `tools/knowledge/models.py:107` defines `Node` with no `candidate_of`,
  `candidate_slug`, `candidate_layout`, `promoted_candidate`, `candidates`,
  or `abandoned_reason` fields.
- `tools/knowledge/parser.py:115` already uses `rglob("*.md")` — subdirectory
  layout is automatically discovered, no parser changes needed.
- `tools/knowledge/parser.py:107` `parse_node_id` splits on the first `.`,
  so `extensive_games.subgame_perfect_equilibrium._cand_A` parses cleanly.
- `tools/knowledge/validator.py:50` `validate_node` is single-node-only; no
  cross-file consistency exists today. Cross-file invariants (canonical ↔
  candidates relationships) need a new validation pass.
- `tools/knowledge/graph.py:20` `build_graph` walks `node.uses` without any
  notion of candidate status; abandoned/candidate nodes would currently
  participate in edges.
- `tools/knowledge/admit.py:78` `admit_node` is staged → admitted. No
  promote/abandon counterparts yet.
- `tools/knowledge/export.py` `home_topic_for_node` + `topic_path` are the
  authoritative routing functions; subdirectory layout must compose with them.
- `tools/knowledge/publish.py:81` `node_detail_payload` and renderer flow
  drive both static-site and JSON output; promoted-proof rendering hooks here.
- `docs/knowledge/nodes/strategic_games/` contains only single-file canonicals
  today — a clean baseline for the regression guard.
- No existing tests cover dir-layout scenarios; new fixtures land in PR 1.

## Design Decisions (locked before PR 1 starts)

1. **Candidate slug character set:** `[a-z0-9_]{1,16}`. **Hyphens are
   disallowed** to keep node ids inside the existing `[a-z_0-9.]` set.
   Issue spec uses `cand-A` informally — we normalise to `cand_a` (lowercase,
   underscore-separated). The directory entry name matches the slug:
   `candidates/cand_a.md` for slug `cand_a`.

2. **Candidate node id form:** `<canonical-id>._<slug>` (single underscore
   prefix in the suffix). Example: `extensive_games.subgame_perfect_equilibrium._cand_a`.
   Rationale: the leading underscore in the suffix makes the candidate id
   visually distinct from a normal child node, and round-trips through
   `parse_node_id` (which splits on the first dot only).

3. **`candidate_layout` marker lives only on `canonical.md`.** Candidates
   themselves are identified by the presence of `candidate_of`. A canonical
   without `candidate_layout: multi` is the legacy single-file form.

4. **`promoted` is graph-grade but NOT in `ADMITTED_STATUSES`** (revised
   after adversarial review). Adding `promoted` to `ADMITTED_STATUSES` would
   silently change validator rules at `validator.py:112,137,170`, double-count
   stats at `stats.py:131`, and cause `FuzzyTitleDupDetector` at
   `lint/_detectors.py:120,166` to flag every canonical-vs-promoted pair as
   a duplicate. Instead PR 1 introduces:
   - `CANDIDATE_STATUSES = frozenset({"candidate", "promoted", "abandoned"})`
   - `PROOF_BEARING_STATUSES = ADMITTED_STATUSES | {"promoted"}` — used by
     `graph.py` and `export.py` where a `promoted` candidate must be treated
     as proof-grade.
   - `ADMITTED_STATUSES` stays `{"admitted", "formalized", "proved"}` exactly.
   - Validator's "node in nodes/ has staged status" rule (`validator.py:114`)
     is loosened to allow `CANDIDATE_STATUSES` under `nodes/` when the node
     has `candidate_of` set.
   PR 1 ships the audit table (which callsites switch to
   `PROOF_BEARING_STATUSES`, which stay on `ADMITTED_STATUSES`) in its PR
   description.

5. **DAG edges:** Only the `promoted` candidate contributes inbound proof-graph
   edges to the canonical. `candidate` and `abandoned` siblings are loaded
   into the node table (so they remain queryable and rendered as alternatives),
   but `build_graph` skips edge creation for them. `uses:` declared on a
   candidate is still validated to exist, just not connected.

6. **Migration trigger:** First call to `candidate spawn` against an existing
   single-file canonical. No global migration. `tools/knowledge/check.py`
   accepts both layouts forever.

7. **Helpers admitted inside a candidate:** Plain admitted nodes living
   anywhere in the topic tree. They are not nested under `candidates/`; if a
   candidate-specific helper graduates, it moves to the topic directory like
   any other admitted node.

8. **Canonical directory accessor:** A canonical's dir is recovered as
   `canonical.file_path.parent`; a candidate's canonical dir is
   `candidate.file_path.parent.parent`. PR 1 ships `canonical_dir(node)`
   in `tools/knowledge/candidate_layout.py` so the formula appears in
   exactly one place.

9. **Topic routing for dir-layout files:** `export.py:172`'s current
   `entry["topic"] = str(node.file_path.parent.name)` is **broken** for
   `nodes/<topic>/<local_id>/canonical.md` (it returns `<local_id>`, not
   `<topic>`). PR 1 fixes this to use `home_topic_for_node(node)` and adds
   a regression test against a fixture tree with both layouts. This fix is
   prerequisite for Success Criterion #2 (graph.json identity after
   migration) and must land before PR 3.

## Success Criteria (from issue #159) → PR mapping

| # | Criterion | Lands in |
| --- | --- | --- |
| 1 | Existing single-file canonicals validate, build DAG, publish unchanged | Regression guard on **every** PR |
| 2 | `candidate spawn` on single-file canonical migrates and validates with same `graph.json` | PR 3 (migrate) + PR 4 (graph.json identity) |
| 3 | Spawn → mark proved → `promote` flips `promoted_candidate`; previous → `abandoned`; page shows new proof | PR 3 (CLI) + PR 4 (render) |
| 4 | Validator rejects a candidate whose statement diverges from canonical | PR 2 |
| 5 | Validator rejects two siblings both with `status: promoted` | PR 2 |
| 6 | Abandoning a candidate does not remove independently-admitted helpers | PR 3 (verify via test) |

---

## Staged PR Plan

PRs run **serially**: PR 1 → PR 2 → PR 3 → PR 4. Each is independently
mergeable, but later PRs assume earlier PRs are in.

### PR 1 — Schema foundation (models + parser + per-node validation)

**Scope:** Data-model groundwork. No behaviour change for existing canonicals.
After this PR, dir-layout files parse and pass per-node validation; cross-file
checks come in PR 2.

- [ ] `tools/knowledge/models.py`:
  - Extend `VALID_STATUSES` with `candidate`, `promoted`, `abandoned`.
  - Add `CANDIDATE_STATUSES = frozenset({"candidate", "promoted", "abandoned"})`.
  - Add `PROOF_BEARING_STATUSES = ADMITTED_STATUSES | {"promoted"}`.
  - `ADMITTED_STATUSES` is **unchanged** — do not add `promoted` to it
    (see Design Decision #4 for rationale).
  - Add fields to `Node`:
    - `candidate_of: str | None = None`
    - `candidate_slug: str | None = None`
    - `candidate_layout: str | None = None` — `"multi"` or `None`
    - `promoted_candidate: str | None = None`
    - `candidates: list[str] = field(default_factory=list)`
    - `abandoned_reason: str | None = None`

- [ ] `tools/knowledge/parser.py`:
  - `parse_node` reads the six new frontmatter fields into the new `Node`
    attributes. Treat missing fields as `None` / empty list.
  - No change to `scan_directory` — `rglob("*.md")` already picks up files
    under `<canonical-id>/canonical.md` and `<canonical-id>/candidates/*.md`.

- [ ] `tools/knowledge/validator.py`:
  - Per-node schema checks for the new fields:
    - `candidate_slug` (when set) must match `^[a-z0-9_]{1,16}$`.
    - `candidate_layout` (when set) must equal `"multi"`.
    - If `candidate_of` is set, then `candidate_slug` must be set,
      `status` must be in `CANDIDATE_STATUSES`, and `kind` must be in
      `STATEMENT_KINDS`.
    - If `candidate_of` is set, then `id` must equal
      `f"{candidate_of}._{candidate_slug}"`.
    - If `candidate_layout == "multi"`, then `candidates` must be a
      non-empty list of strings (slug-form) and either
      `promoted_candidate is None` or `promoted_candidate in candidates`.
    - A node with `candidate_layout == "multi"` set must **not** have
      `candidate_of` set (canonical vs candidate are exclusive).
    - **Staged rejection:** if `is_staged_dir` is true and the node has
      `candidate_of` or `candidate_layout` set → error
      ("multi-candidate layout is not supported under staged/").
  - Loosen the directory-status check so candidates in `nodes/` may carry
    `status` in `CANDIDATE_STATUSES` without tripping the "node in nodes/
    has staged status" rule.

- [ ] **Topic routing fix** in `tools/knowledge/export.py:172`:
  - Replace `entry["topic"] = str(node.file_path.parent.name)` with
    `entry["topic"] = home_topic_for_node(node)`.
  - This is a prerequisite for the dir layout — without it,
    `nodes/<topic>/<local_id>/canonical.md` would emit `topic=<local_id>`.
  - **Regression guard:** the bundled `docs/knowledge` (all single-file
    canonicals today) must produce a byte-identical `graph.json` before
    and after this change. Capture the pre-change output once
    (`/tmp/graph-before.json`), run the change, diff. Add the captured
    output to `tests/fixtures/` so future PRs can re-verify cheaply.

- [ ] **`ADMITTED_STATUSES` audit table** — file this in the PR description:
  - `validator.py:112,137,170` → stay on `ADMITTED_STATUSES`.
  - `stats.py:131` → stay on `ADMITTED_STATUSES` (canonical-only count).
  - `lint/_detectors.py:120,166` → stay on `ADMITTED_STATUSES`, **plus**
    suppress detector findings when one node has `candidate_of` set and
    the other is its canonical. Land the suppression in PR 1 to keep
    PR 2's check output clean.
  - `lint/_llm.py:99` → same as `_detectors.py`.
  - `graph.py` (PR 2) and `export.py` (PR 4) → switch the relevant
    branches to `PROOF_BEARING_STATUSES`.

- [ ] `tests/test_models_candidate.py`: parametric tests over the new
      schema rules. Covers both accepting valid frontmatter and rejecting
      each violation class above. Use in-memory parsing only (no file IO).

- [ ] `tests/test_parser_candidate_layout.py`: tmpdir fixture creating
      `nodes/topic/canonical_id/canonical.md` and
      `nodes/topic/canonical_id/candidates/cand_a.md`; assert
      `scan_directory` returns both with the correct field values.

- [ ] Run the full suite: `uv run --extra dev python -m pytest -q`.

- [ ] Run the structural check unchanged: `uv run python -m tools.knowledge.check docs/knowledge` — output must match `main` baseline (regression guard).

**Done when:**
- All existing tests pass.
- New tests pass.
- `check` on the bundled `docs/knowledge` produces the same diagnostics as
  before this PR.
- No file in `tools/knowledge/` exceeds 800 lines.

**Out of scope (deferred to PR 2):** Cross-file validation (canonical ↔
candidates statement equality, sibling promoted-uniqueness, location
constraints).

### PR 2 — Cross-file validation + graph DAG integration

**Scope:** Make the validator and DAG builder aware of the canonical ↔
candidates relationship. After this PR, malformed dir layouts fail
`check`, and only `promoted` candidates contribute proof-graph edges.

- [ ] New `tools/knowledge/candidate_layout.py`:
  - `CanonicalGroup` dataclass holding `canonical: Node`,
    `candidates: list[Node]`, `dir_path: Path | None`.
  - `canonical_dir(node) -> Path | None`:
    - If `node.candidate_layout == "multi"`: returns `node.file_path.parent`
      (canonical sits at `<topic>/<local_id>/canonical.md`).
    - If `node.candidate_of` is set: returns `node.file_path.parent.parent`
      (candidate sits at `<topic>/<local_id>/candidates/<slug>.md`).
    - Else: `None`.
    Single source of truth — every other consumer calls this helper.
  - `discover_canonical_groups(nodes: list[Node]) -> list[CanonicalGroup]`:
    walks the node list, matches candidates to their canonical by
    `candidate_of`, and recovers `dir_path` via `canonical_dir`.
  - `canonical_proof_source(canonical_id, nodes_by_id, groups_by_canonical)
    -> Node`: returns the canonical itself for single-file canonicals;
    returns the `status: promoted` sibling for multi-candidate canonicals;
    returns the canonical (with `verification.proof: pending`) if no
    sibling is promoted yet. Used by PR 4's renderer.
  - `validate_canonical_groups(groups, nodes_by_id) -> list[Diagnostic]`:
    cross-file rules listed below.

- [ ] Cross-file invariants enforced in `validate_canonical_groups`:
  - Each candidate's `candidate_of` must resolve to a canonical node in the
    node table; missing canonical → error on the candidate.
  - For canonicals with `candidate_layout == "multi"`:
    - `candidates` field must equal the sorted slug list of discovered
      candidate files.
    - `promoted_candidate` must either be `None` (and no sibling has
      `status: promoted`) or name a slug whose file exists with
      `status: promoted`.
    - At most one sibling may have `status: promoted`. Two or more →
      error citing both file paths.
    - File layout: `canonical.md` must live at
      `<topic>/<canonical_local_id>/canonical.md` and each candidate at
      `<topic>/<canonical_local_id>/candidates/<slug>.md`. Mismatches →
      error.
    - **Statement equality:** extract the body content up to the proof
      marker (either `*Proof.*` or `**Proof.**` — reuse the constants
      from `admit._has_proof_block` via a shared helper
      `proof_block_start(body) -> int | None` introduced in
      `candidate_layout.py`). Normalise: collapse runs of whitespace
      to a single space, strip leading/trailing whitespace, strip
      trailing punctuation. Require byte equality between canonical's
      and candidate's normalised statement segment. Divergence → error
      on the candidate citing both file paths.
    - `kind` of each candidate must equal `kind` of canonical.

  - For candidates living in a flat-file canonical's tree (no
    `canonical.md` exists yet): error — the file layout is malformed.

- [ ] `tools/knowledge/graph.py`:
  - In `build_graph`, after the node table is constructed, walk
    candidates. A candidate with `status == "promoted"` contributes its
    `uses` edges **on behalf of its canonical** (the canonical itself
    retains `verification.proof: pending` until promotion, but the DAG
    treats the promoted candidate as the proof source).
  - `candidate`/`abandoned` siblings stay in `g.nodes` but contribute no
    edges in either direction.
  - When a candidate's `uses` references a node, the dependency rule
    "mathematical node uses proof-plan must use target" applies to it
    unchanged.

- [ ] `tools/knowledge/check.py`: call `discover_canonical_groups` and
      `validate_canonical_groups`; merge their diagnostics into the
      existing pipeline. Keep the call deterministic (sorted by file path
      before emitting).

- [ ] `tests/test_validator_candidates.py`: each rule above gets at least
      one positive (accepting) and one negative (rejecting) test using
      tmpdir fixtures with `canonical.md` + sibling candidates. **Must
      include a nested-topic fixture** (e.g.
      `nodes/extensive_games/subgames/<local_id>/canonical.md`) to
      guard against the `parent.parent` formula breaking under deeper
      topic hierarchies — `canonical_dir` is the only function allowed
      to compute the result.

- [ ] `tests/test_graph_candidates.py`:
  - Promoted candidate's `uses` shows up in `KnowledgeGraph.edges` keyed
    by canonical id? **No** — keyed by the candidate's own id. Document
    this in the docstring. The publisher in PR 4 resolves
    canonical→promoted-candidate when rendering edges.
  - Abandoned candidate's `uses` contributes **no** edges.
  - `candidate` (unverified) sibling contributes no edges.

- [ ] Regression: run `uv run python -m tools.knowledge.check docs/knowledge`
      and confirm output is unchanged vs `main`.

**Done when:**
- All six success criteria #4 / #5 cases land as failing-now-passing tests.
- Cross-file diagnostics emit before publish would run.
- Single-file canonicals still build the same graph.

### PR 3 — `candidate` CLI + promote / abandon / spawn / list

**Scope:** End-to-end authoring workflow. After this PR, an agent can run a
single command to create, promote, or abandon a candidate, and the resulting
files validate.

- [ ] New `tools/knowledge/candidate.py`:
  - `spawn_candidate(canonical_id, *, knowledge_root, slug=None) -> SpawnResult`
    - Locate the canonical: first `nodes/**/<local_id>.md` (single-file)
      or `nodes/**/<local_id>/canonical.md` (dir form).
    - If single-file form: migrate.
      - Snapshot the original file's full text and path into memory
        (used for rollback on any subsequent failure in this spawn).
      - **Split the body at the proof boundary** using
        `proof_block_start` from `candidate_layout.py` (PR 2 ships the
        helper, same source of truth as the validator). The portion
        before the marker is the "statement segment"; the portion from
        the marker onward is the "proof segment".
      - Write `<local_id>/canonical.md`: keeps the original id, kind,
        and topic; body is **the statement segment only** (proof
        segment is removed); status is preserved (e.g. `admitted` →
        `admitted`); inject `candidate_layout: multi`,
        `promoted_candidate: cand_a`, `candidates: [cand_a]`;
        `verification.proof` is preserved from the original file —
        because the canonical now has a verified proof via `cand_a`.
      - Write `<local_id>/candidates/cand_a.md`: id rewritten to
        `<canonical_id>._cand_a`; `candidate_of: <canonical_id>`,
        `candidate_slug: cand_a`, `status: promoted`,
        `kind` preserved; body is **the statement segment plus the
        proof segment** (faithful copy of the original proof body
        below the statement); `verification` preserved.
      - Delete the original `<local_id>.md` file after both writes
        succeed.
      - Result: canonical holds only the statement; `cand_a` holds
        statement + proof; rendering pipeline (PR 4) emits exactly
        one proof per page.
    - Compute slug for the *new* spawn:
      - If user passed `--slug X`, validate against
        `^[a-z0-9_]{1,16}$` and check non-collision.
      - Else auto-assign the next free `cand_a`, `cand_b`, …
    - Write `<local_id>/candidates/<slug>.md`:
      - frontmatter: `id`, `kind`, `status: candidate`, `candidate_of`,
        `candidate_slug`, `uses` copied from canonical baseline, empty
        `verification.proof`.
      - body: canonical's statement block copied verbatim; empty proof
        block placeholder (`*Proof.*` followed by `TODO`).
    - Append the new slug to `canonical.md`'s `candidates` list.

  - `promote_candidate(candidate_path, *, knowledge_root) -> PromoteResult`
    - Parse the candidate; require `status` in `{"candidate", "promoted"}`
      and `verification.proof == "accepted"`.
    - Run the existing admission-evidence checks via
      `admit.admission_evidence_diagnostics` against the candidate (treat
      it as a statement-kind node).
    - Use `discover_canonical_groups` (PR 2) to find the canonical and
      siblings; abort if the candidate's group fails
      `validate_canonical_groups`.
    - Flip the previously-promoted sibling (if any) to
      `status: abandoned` and append an `abandoned_reason`
      (`"superseded by <new-slug> at <ISO-timestamp>"`).
    - Set this candidate's `status: promoted`.
    - Rewrite `canonical.md`: `promoted_candidate: <new-slug>` and
      `verification.proof: accepted` (the canonical now has a verified
      proof via this candidate).
    - Emit `reviews/<canonical_id>/promotion-<slug>-<UTC-iso>.md`
      capturing the decision: which slug was promoted, which was
      retired, the diagnostics output, timestamp.

  - `abandon_candidate(candidate_path, *, knowledge_root, reason: str)`
    - Reject if the candidate's current `status == "promoted"` (require
      `promote` of a different candidate first).
    - Set `status: abandoned`, `abandoned_reason: <reason>`.
    - Emit `reviews/<canonical_id>/abandon-<slug>-<UTC-iso>.md`.

  - `list_candidates(canonical_id, *, knowledge_root)` — print slug,
    status, abandoned_reason (if any), file path. Plain text + `--json`.

  - **Atomicity / rollback strategy.** Each operation takes an
    in-memory snapshot before the first write:
    `snapshot = [(path, optional_original_bytes), ...]` covering every
    file the operation will create, overwrite, or delete. Writes go
    through a single helper `_apply_writes(snapshot, target_writes)`
    that performs all writes, then runs
    `validate_canonical_groups` + `build_graph`. On any failure, the
    helper restores every snapshotted path (writing back originals,
    deleting newly-created files) and re-raises. Filesystem
    cross-process atomicity is **not** required — see concurrency
    guidance below.

  - **Concurrency guidance.** Per `AGENTS.md`, this repo supports
    parallel agents. The CLI does not implement file locking, but it
    does:
    - Compute the next free auto-slug by globbing
      `<local_id>/candidates/cand_*.md` and choosing the lowest unused
      letter; if a collision is detected after write (via a re-read
      followed by `discover_canonical_groups`), retry up to 3 times
      with a fresh slug.
    - Validate the post-write state via `build_graph`; if another agent
      wrote `canonical.md` in between, the validation will fail and
      rollback fires.
    Document in the CLI's `--help` that parallel `spawn` operations
    against the *same* canonical id are racy and should be serialised
    by the calling workflow.

  - `main(argv)` exposes:
    - `python -m tools.knowledge.candidate spawn <canonical-id> [--slug <slug>]`
    - `python -m tools.knowledge.candidate promote <candidate-path>`
    - `python -m tools.knowledge.candidate abandon <candidate-path> --reason "..."`
    - `python -m tools.knowledge.candidate list <canonical-id>`

- [ ] `pyproject.toml`: register
      `mdblueprint-candidate = "tools.knowledge.candidate:main"`.

- [ ] `tests/test_candidate_spawn.py`:
  - **Migration round-trip:** spawn against a single-file canonical and
    confirm: original file gone; `canonical.md` + `candidates/cand_a.md`
    + `candidates/cand_b.md` (for the new request) exist;
    `discover_canonical_groups` accepts the resulting tree;
    `build_graph` produces the same edge set as the pre-migration state.
  - **Proof body not duplicated:** assert `canonical.md` does **not**
    contain `*Proof.*` or `**Proof.**`; assert `candidates/cand_a.md`
    contains exactly one proof marker.
  - **Success criterion #2:** post-migration `graph.json` value-equal
    (after JSON-deserialise sort) to the pre-migration `graph.json` —
    at least for the canonical and its forward closure. Compare against
    a captured snapshot under `tests/fixtures/graph_json_pre_migration.json`
    so the test runs without rebuilding `main` baselines.

- [ ] `tests/test_candidate_promote.py`:
  - Spawn → mark new candidate proof as accepted → `promote` →
    canonical's `promoted_candidate` and `verification.proof` flip;
    previous promoted slug becomes `abandoned` with reason; a review
    report appears under `reviews/`.
  - Success criterion #3: render output (mocked via the renderer entry
    point) names the new candidate's proof body — actual rendering test
    lands in PR 4.

- [ ] `tests/test_candidate_abandon.py`:
  - Abandoning a non-promoted candidate flips status + reason; does not
    touch `canonical.md`.
  - Abandoning the currently-promoted candidate is rejected with a clear
    error.
  - **Success criterion #6:** the test creates a separately-admitted
    helper node in the topic dir, runs `abandon` on a candidate whose
    `uses` references that helper, and asserts the helper file is
    untouched on disk and still admitted.

- [ ] Regression: `check docs/knowledge` still clean on `main` baseline
      knowledge base.

**Done when:**
- `mdblueprint-candidate spawn` migrates a single-file canonical and
  passes `check`.
- Promote/abandon writes are atomic-on-failure (no partial state).
- Every success criterion from the issue is exercised by at least one
  passing test (criterion #1 is the regression guard run on every PR).

### PR 4 — Publish, `graph.json`, and docs

**Scope:** Render promoted proofs on canonical pages, expose abandoned
siblings in an expander, surface `candidate_layout` in `graph.json` and
the topic payloads, and update authoring docs.

- [ ] `tools/knowledge/export.py`:
  - `write_graph_json`: for canonicals with `candidate_layout == "multi"`,
    add `candidate_layout: "multi"`, `promoted_candidate: <slug>`,
    `candidate_siblings: [<slug>, ...]` to the canonical's node entry.
    Candidate sibling nodes themselves are written with
    `kind: "candidate"` overlay (preserve original `kind` under
    `canonical_kind`) so the graph frontend can group them.
  - Single-file canonicals get **no new keys** — preserve byte identity
    for the regression case (success criterion #1 → success criterion #2
    `graph.json` parity after migration is verified by the round-trip test
    in PR 3, plus a fresh PR 4 fixture).

- [ ] `tools/knowledge/renderer.py`:
  - When rendering a canonical with `candidate_layout == "multi"`, the
    main proof body is the promoted candidate's proof block; the
    canonical's own body (statement + cross-references) renders above it.
  - Add an "Alternative proof attempts (N)" `<details>` expander listing
    abandoned siblings: title, `abandoned_reason`, link to the candidate
    file.
  - `candidate` (unverified) siblings render in a separate expander
    ("Work-in-progress proofs (M)") only when N > 0.
  - For canonicals with no `candidate_layout`, render exactly as before.

- [ ] `tools/knowledge/publish.py`: no changes expected if renderer
      changes are self-contained; verify by diffing site output before
      and after on the bundled knowledge base.

- [ ] `tests/test_publish_candidates.py`: golden fixture with one
      multi-candidate canonical, one promoted candidate, one abandoned
      candidate, one work-in-progress candidate. Assertions:
  - canonical's rendered HTML, when stripped of tags and normalised
    (whitespace-collapse), contains the promoted candidate's proof
    body normalised the same way. **Do not** assert byte-identity of
    rendered HTML — the renderer's KaTeX/Markdown pass introduces
    structural HTML that has no source-level analogue.
  - canonical page contains an "Alternative proof attempts (1)" expander
    listing the abandoned slug with its reason.
  - canonical page contains a "Work-in-progress proofs (1)" expander.
  - `graph.json` for the canonical has `candidate_layout: "multi"` and
    `promoted_candidate: <slug>`.
  - Single-file canonical's rendered HTML in the same fixture has
    **none** of `candidate_layout`, `promoted_candidate`,
    `candidate_siblings` keys (regression for graph.json identity).

- [ ] `tests/test_export_candidates.py`: standalone test on
      `write_graph_json` against tmpdir fixtures, asserting key presence
      / absence for the two layouts.

- [ ] Regression: render the bundled `docs/knowledge` and diff against
      a freshly-built `/tmp/mdblueprint-site-baseline/` from `main`. Only
      timestamp-like diffs are allowed.

- [ ] Docs:
  - `docs/node-format.md`: new "Multi-candidate layout" section covering
    frontmatter keys, slug rules, migration behaviour, and the example
    directory tree.
  - `docs/architecture.md`: short paragraph noting that canonical pages
    pull proofs from their promoted candidate when `candidate_layout: multi`.
  - `AGENTS.md`: add `mdblueprint-candidate` to the dev-commands list.

**Done when:**
- All four success criteria touching publish (#1 regression, #2 graph.json
  parity, #3 page renders new proof, #5 indirect — render rejects
  inconsistent state) pass.
- Site output for the bundled `docs/knowledge` is unchanged.
- `docs/node-format.md` includes a valid example a fresh agent can copy.

---

## Risk Notes

- **Migration write order (PR 3):** `spawn`'s migration touches three files
  (delete original, create `canonical.md`, create `candidates/cand_a.md`).
  Use a snapshot-and-rollback strategy: read all three target paths up front,
  perform writes, run validation, and on failure restore originals. Filesystem
  atomicity isn't required — we control the only writer.

- **Statement-equality normalisation (PR 2):** Too lax → divergent proofs
  pass. Too strict → trivial whitespace differences break promotion. Start
  with whitespace-collapse + trailing-punctuation strip; expand only if a
  real fixture demands it. Track regressions with golden fixtures.

- **DAG semantics for `promoted` (PR 2):** The graph builder must keep the
  candidate's id in `g.nodes` *and* its `uses` edges. If anything downstream
  walks edges keyed on canonical ids, we may need a resolver helper
  (`canonical_proof_source(canonical_id, graph) -> Node`). Plan for this
  helper in PR 2; consumers in PR 4 use it.

- **`promoted` ⊂ `ADMITTED_STATUSES` (PR 1):** Adding `promoted` to the
  admitted set means existing checks treating "in nodes/, status ∉
  STAGED_STATUSES" as admitted continue to work. Audit `parser.py`,
  `validator.py`, `admit.py`, `graph.py`, `export.py`, `publish.py`
  consumers of `ADMITTED_STATUSES` once and document the audit results in
  the PR description.

- **graph.json identity (PR 4 success #2):** Achievable only if single-file
  canonicals produce zero new keys. The renderer/exporter must branch on
  `candidate_layout` presence, not on directory shape, to avoid leaking
  multi-layout artefacts into the single-file path.

## Open Questions (tracked in issue #159)

1. **Sibling helpers under `candidates/`:** Should helper lemmas created
   inside a candidate live under `candidates/` or in the topic root from
   the start? Plan position: only the candidate file lives in
   `candidates/`. Helpers are normal admitted nodes in the topic root.
   Confirm with reviewer before PR 3.

2. **Reviews directory layout:** Should the promotion / abandonment
   reviews mirror the canonical's topic path
   (`reviews/<topic>/<canonical-local-id>/promotion-...md`) or stay flat
   (`reviews/<canonical-id>/promotion-...md`)? Plan position: flat, keyed
   by full canonical id. Easy to grep, no topic-rename churn.

3. **Should `staged/` ever support dir layout?** Plan position: no, per
   the issue. Validator must explicitly reject `candidate_of` /
   `candidate_layout` on nodes whose `file_path` is under `staged/`.

## Plan Mutation Protocol

If a PR's scope shifts during execution:

1. Update the relevant PR's checkbox list *in this file* before opening
   the PR.
2. Note the rationale in the PR description, citing the success
   criteria the change still satisfies.
3. If a success criterion would slip past PR 4, file a follow-up issue
   and link it from this file's "Risk Notes" section before merging.

## Plan Mutations (executed)

**2026-05-28 — PR 3 edge-ownership + criterion #2 relaxation.**

While implementing PR 3 a design fork surfaced that the plan left open:
both the canonical and its promoted candidate could contribute `uses`
edges, which would double every dependency edge. Locked decision:

- **The promoted candidate is the sole edge source.** A multi-candidate
  canonical carries `uses: []`; all proof-dependency edges live on the
  promoted candidate (keyed by `<canonical>._<slug>`), consistent with
  the PR 2 graph builder. `promote` only flips statuses + the
  `promoted_candidate` pointer — it never syncs `uses`, so there is
  exactly one edge owner at all times.
- Migration moves the original single-file node's `uses` onto `cand_a`
  (the promoted migrated proof) and sets the canonical's `uses` to `[]`.
- A freshly spawned candidate copies its baseline `uses` from the
  *currently promoted candidate* (via `canonical_proof_source`), not from
  the now-empty canonical.

Consequence: **Success Criterion #2's literal "same `graph.json`" is not
achievable** — migration intentionally moves the proof's dependency edges
from the `topic.thm` node to the `topic.thm._cand_a` node, so the
forward-closure entries change. Relaxed criterion #2 (still meaningful):

> After migration, (a) `check` passes, (b) `discover_canonical_groups`
> accepts the tree, (c) the set of dependencies *reachable from the
> canonical, resolving through its promoted candidate* equals the
> pre-migration `uses` set.

PR 3 tests assert this relaxed form; PR 4's `graph.json` work keeps
single-file output byte-identical (criterion #1) and only adds keys for
multi-layout canonicals.

## Adversarial Review Log

**2026-05-27 (initial review, RED → GREEN after revisions):**

Five RED findings fixed before this revision shipped:

1. `export.py:172` topic routing was broken for dir-layout — fixed
   inline in PR 1 with regression fixture.
2. `dir_path = file_path.parent.parent` was wrong for canonical files —
   replaced by a centralised `canonical_dir()` helper.
3. `_check_duplicate_topic_ids` nested-topic interaction — covered by
   nested-topic fixture in PR 2 tests.
4. `promoted` was originally added to `ADMITTED_STATUSES` with broad
   blast radius — split into a new `PROOF_BEARING_STATUSES` set with an
   explicit per-callsite audit table; lint detectors get a candidate
   suppression pass in PR 1.
5. Spawn migration was copying the proof body to both canonical and
   candidate — now splits at the proof marker and asserts no duplication.

Seven YELLOW findings folded in: shared `proof_block_start` helper for
boundary detection; `canonical_proof_source` helper relocated to PR 2;
staged-rejection rule in PR 1; explicit snapshot-rollback strategy;
captured-fixture baseline instead of live-baseline diffing; auto-slug
collision retry; rendered-HTML test specified to compare normalised text
not bytes.
