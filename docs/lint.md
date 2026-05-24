# `mdblueprint-lint`

`mdblueprint-lint` is the project's structural and semantic linter. It
extends `mdblueprint-check` (which enforces the publish gate) with rule-
coded findings that surface duplication, structural smells, Lean-link
mismatches, and editorial workflow gaps.

## Running it

```bash
uv run mdblueprint-lint docs/knowledge
uv run mdblueprint-lint docs/knowledge --json
uv run mdblueprint-lint docs/knowledge --strict-warnings
```

`--strict-warnings` makes warning-level findings exit non-zero. Info-level
findings never affect the exit code by themselves.

LLM-backed detectors are off by default:

```bash
uv run mdblueprint-lint docs/knowledge --llm --llm-budget 50
```

`--llm-budget` caps total LLM calls per run; cached judgements still count
toward dedupe but not toward the budget. `--cache-dir` defaults to
`.mdblueprint/lint-cache`; `--no-cache` disables persistence (intra-run
dedupe still works).

## Configuration (`mdblueprint.yml`)

```yaml
lint:
  fuzzy_threshold: 0.92                  # LINT_FUZZY_DUP / LINT_STAGED_OVERLAP
  semantic_candidate_threshold: 0.75     # LINT_SEMANTIC_DUP candidate selection
  plan_promote_severity: info            # LINT_PLAN_PROMOTE level: info | warning
  hierarchy_inversion_severity: warning  # LINT_HIERARCHY_INVERSION level: info | warning
```

## Rule reference

### `LINT_FUZZY_DUP` — Near-duplicate admitted nodes

**Trigger.** Two admitted nodes whose normalized titles (or, as a
secondary signal, the contents of their `## Statement` sections) reach
similarity ≥ `lint.fuzzy_threshold`.

**Level.** `warning`. `related` carries the other node id.

**Example.**

```
topic.x  title: "Group Identity Is Unique"
topic.y  title: "Group Identity Is Unique."
```

**How to fix.** Pick the canonical node; delete the duplicate (or mark it
`status: deprecated` and add a `previous_ids:` redirect if the URL needs
to live on).

### `LINT_STAGED_OVERLAP` — Staged candidate restates an admitted node

**Trigger.** A staged node whose normalized title/statement is similar
(≥ `lint.fuzzy_threshold`) to an already-admitted node.

**Level.** `warning`. `related` carries the admitted node id.

**How to fix.** Either retire the staged candidate (it adds nothing) or
rewrite it to be genuinely distinct before the next admission round.

### `LINT_REDUNDANT_DEP` — Direct `uses` edge implied by a transitive path

**Trigger.** Node `T` has `uses: [..., P, ...]` and reaches `P` through
another path of length ≥ 2 in the dependency graph.

**Level.** `info`. `related` carries the redundant prerequisite id.

**Example.** `T.uses = [A, B]`, `B.uses = [A]` ⇒ `T → A` is redundant.

**How to fix.** Remove the redundant id from the dependent node's `uses:`.

### `LINT_ORPHAN` — Node with no incoming or outgoing dependencies

**Trigger.** A node with `in_degree == 0` and `out_degree == 0` in the
dependency graph, **and** no proof-plan attachment in either direction.

**Level.** `info`.

**How to fix.** Either wire the node into the graph by adding `uses:` /
attaching a plan, or remove it. There is no exception list this release;
genuine standalone topic anchors will surface here.

### `LINT_LEAN_KIND` — Lean declaration kind contradicts mdblueprint kind

**Trigger.** Node `kind=definition`/`concept` ties to a Lean `theorem`
or `lemma`, or node `kind=theorem`/`lemma`/`proposition`/`external-theorem`
ties to a Lean `def`/`abbrev`/`structure`/`class`/`inductive`/`instance`.

**Level.** `warning`. `related` carries the Lean declaration name.

**How to fix.** Either the node's `kind:` is wrong or the wrong Lean
entity got wired in. Fix whichever is wrong.

**Skip behaviour.** When no Lean repository is configured (or every
configured repo fails to index), the detector emits one
`info` "lean index not available; skipping LINT_LEAN_KIND" instead of
running, so the rest of the lint pass stays useful.

### `LINT_PLAN_PROMOTE` — Theorem has a completed plan but is not `proved`

**Trigger.** Theorem-like node `T` with `status != "proved"` and at least
one attached plan `P` satisfying:
- `P.status` is `formalized` or `proved`
- every transitive ancestor of `P` is itself `formalized`/`proved` or a
  definition-kind node.

**Level.** `info` by default. Set `lint.plan_promote_severity: warning`
in `mdblueprint.yml` to make it strict.

**How to fix.** Run `uv run python -m tools.knowledge.promote_via_plan
docs/knowledge` to auto-write `status: proved` and the
`proved_via_plan: <plan_id>` marker, or do the same by hand. The
detector picks the same canonical plan as the CLI (selected plan wins;
ties break by sorted plan id), so the two stay in agreement.

### `LINT_HIERARCHY_INVERSION` — Parent-topic content depends on a subtopic

**Trigger.** A `uses` edge from a node living in a strict descendant
subtopic into a node whose home topic is the ancestor — i.e. parent-topic
content imports specialised subtopic material. Almost always an editorial
mistake: either the parent-tagged node should move down into the
relevant subtopic (change its `primary_topic`), or the dependency on the
specialised material should be removed.

**Level.** `warning` by default. Set `lint.hierarchy_inversion_severity:
info` in `mdblueprint.yml` to demote.

**Example.** Node `T` has `primary_topic: alg` and `uses:
[alg.cohomology.cup_product]`. The prereq's home is the strict
descendant `alg.cohomology`; the detector flags this edge.

**How to fix.** Move `T` to `primary_topic: alg.cohomology` (or to the
deepest common ancestor of all its dependencies) — or drop the
subtopic-level dependency.

**Healthy direction stays silent.** A node in `alg.cohomology` depending
on a node in `alg` (subtopic uses parent's basics) is fine — the
detector only fires when the arrow points up the hierarchy in the
unhealthy direction.

### `LINT_TOPIC_CYCLE` — Sibling subtopics aggregate into a cycle

**Trigger.** Two sibling child topics `A` and `B` under a common parent
each have nodes that depend on nodes in the other, producing an `A ↔ B`
loop when the topic-level overview is aggregated. The underlying
node-level DAG stays acyclic; this is purely an aggregation observation.

**Level.** `info` (not configurable; the aggregation cycles are
by-design allowed but worth surfacing).

**Example.** `extensive_game.core` contains nodes that
`extensive_game.imperfect_information` depends on, and vice-versa —
the `extensive_game` topic overview shows both arrows.

**How to fix.** Often nothing needs to change — the cycle reflects
genuine cross-pollination between the two subtopics. If the cycle is
unwanted, either merge the two child topics, or relocate the few
"bridge" nodes so they live above (or beside) the cycle.

### `LINT_SEMANTIC_DUP` — LLM-judged semantic duplicate (`--llm` only)

**Trigger.** Admitted pair whose fuzzy ratio reaches
`lint.semantic_candidate_threshold` (default `0.75`, below the
`fuzzy_threshold` so the deterministic detector wouldn't have flagged
it). The detector asks the configured LLM whether the two nodes state
the same theorem; `same: true` ⇒ warning.

**Level.** `warning`. `related` carries the other node id.

**Caching.** Decisions are content-hashed into `.mdblueprint/lint-cache/`
(or wherever `--cache-dir` points). Cache survives across runs and is
invalidated when the prompt version constant or any node's
title/statement changes.

**How to fix.** Same as `LINT_FUZZY_DUP`: pick a canonical node and
retire or redirect the duplicate.

### `LINT_LEAN_ALIGN` — Statement does not align with Lean declaration (`--llm` only)

**Trigger.** A theorem-like or definition-like node carrying a Lean
declaration that resolves cleanly through the index, with the LLM
judging that the Markdown statement and Lean signature describe
different things (`aligned: false`).

**Level.** `warning`. `related` carries the Lean declaration name.

**How to fix.** Either the Markdown statement is sloppy and needs
tightening, or the wrong Lean entity was wired in. Fix whichever is
wrong; consider also raising the issue in the corresponding source
review if the Lean side is right and the Markdown is informal.

## How LLM-backed detectors degrade

Every LLM-backed detector:

- Stays silent (returns no diagnostics) when `--llm` is unset.
- Emits one info diagnostic and returns early when its required
  resources are missing (`LINT_LEAN_KIND` / `LINT_LEAN_ALIGN` when no
  index is configured).
- Emits one info diagnostic and stops when `--llm-budget` is reached;
  unprocessed candidates are silently skipped (re-run after raising the
  budget to pick them up).
- Falls back to one info diagnostic per pair when the model response
  fails to parse; the cache stores the failure so the model is not
  re-asked until prompt-version changes or the cache is cleared.

## Adding a new detector

See `tools/knowledge/lint/_detectors.py` for the deterministic-detector
template and `tools/knowledge/lint/_llm.py` for the LLM-backed template.
The `Detector` protocol in `tools/knowledge/lint/_core.py` is the source
of truth; everything else plugs in via `_default_detectors(config, ...)`.
