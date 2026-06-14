---
name: mdblueprint-graph-refactor-review
description: Use when reviewing an mdblueprint knowledge base for graph-structure refactors, including dependency cleanup, formulation-sensitive impact analysis, topic taxonomy moves, duplicate or overlap triage, merge/split/generalization proposals, proof-plan route separation, Lean/topic divergence, or impact analysis before editing nodes.
---

# mdblueprint-graph-refactor-review

Review mdblueprint node content and deterministic graph evidence, then propose
bounded refactor actions.

## When to use

When reviewing an existing knowledge base for dependency cleanup, topic taxonomy
changes, formulation-sensitive descendant impact, duplicate or overlap triage,
merge/split/generalization proposals, proof-plan route separation, Lean/topic
divergence, or impact analysis before editing nodes.

This skill is for analysis and proposal writing. It is not for automatic
admitted-node rewrites.

## Workflow

1. Define the scope: whole KB, topic, node, lint finding, or proposed edit.
2. Read `AGENTS.md`, `docs/agent-contracts.md`, `docs/node-format.md`,
   `docs/topic-model.md`, `docs/lint.md`, and `docs/publisher-and-dag.md`.
3. Establish the deterministic baseline:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.check <knowledge-root>
   uv --cache-dir /tmp/uv-cache run mdblueprint-lint <knowledge-root> --json
   uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.stats <knowledge-root> --json
   ```

4. Choose the staged-node scope before interpreting missing dependencies:

   - In `admitted+staged` mode, pass `--include-staged` to bounded evidence
     tools. Treat staged nodes as existing graph nodes for refactor analysis:
     they can satisfy dependency existence, reachability, duplicate/overlap,
     topic, and formulation-impact questions. Still label their staged status
     and do not imply admission.
   - In `admitted` mode, build or consult a staged id index before writing
     missing-node requests. If a dependency id is absent from the admitted graph
     but present under `staged/`, do not write a duplicate request and do not
     introduce a staged-promotion proposal. Record it as outside the admitted
     scope or as a human/admission-referee decision.

5. Build a bounded refactor evidence bundle for target-node or target-topic work:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_pack <knowledge-root> --target <node-id>
   uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_pack <knowledge-root> --topic <topic-id>
   ```

   Use the pack's graph neighborhoods, body references, lint findings, and
   formulation-impact hints as evidence, not as automatic refactor decisions.

6. Inspect the minimal node set needed: target, direct dependencies, reverse
   dependencies, sibling topic nodes, and staged overlaps when in scope.
7. For a proposal that modifies, weakens, strengthens, deletes, or replaces a
   node or dependency, read `references/formulation-impact.md`. Graph
   reachability is only the first pass; inspect whether descendant statements
   survive because of the precise formulations of their other ancestors.
8. Classify each proposed action:
   - `mechanical-safe`: deterministic cleanup such as a clearly redundant edge;
   - `semantic-review`: requires mathematical judgment or human confirmation;
   - `request-needed`: requires a `docs/knowledge/requests/` file first;
   - `blocked`: insufficient evidence or failing baseline checks.
9. Apply the generality gate when a proposal generalizes, splits, merges, or
   rehomes mathematical content. Ask what the most general useful form is,
   whether the current node has that form, and what assumptions might be
   removable. Put uncertain answers in the report or a request, not in admitted
   truth.
10. Before writing the final report, run a refinement pass:

   - Rank semantic refactor candidates ahead of lint-hygiene candidates unless
     the lint cleanup is genuinely low-risk, high-impact, and implementation
     ready. Formulation-sensitive dependency changes, duplicate/overlap
     decisions, split/generalization candidates, staged/admitted overlaps, topic
     ownership questions, and high-impact prose-dependency findings should not
     be crowded out by easy redundant-edge cleanup.
   - Reclassify policy decisions such as broad Lean/topic divergence or topic
     ownership as `semantic-review` or `needs-human-review`, not
     `mechanical-safe`.
   - Check major baseline signals that are not final proposals. At minimum,
     review `LINT_FUZZY_DUP`, `LINT_STAGED_OVERLAP`, `LINT_TOPIC_CYCLE`,
     high-impact `LINT_PROSE_DEP`, and high-degree nodes or topics from stats.
     Record why each important skipped signal was outside scope, lower priority,
     already covered by another proposal, blocked by missing evidence, or better
     handled by another agent.
   - Move speculative or low-value operations out of the dry-run plan if they
     would distract from more valuable semantic proposals.

11. Produce a structured report. Use
   `references/refactor-report-schema.md` for durable reports.
   Validate durable reports before treating proposals as actionable:

   ```bash
   uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_report_check <knowledge-root> <report-path>
   ```

12. For concrete mechanical actions, write an explicit dry-run plan using
    `references/dry-run-plan-schema.md` and simulate it before editing files:

    ```bash
    uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_dry_run <knowledge-root> <plan.yml> --json
    ```

    Add `--include-staged` to the dry-run command when the report uses
    `admitted+staged` mode. Node additions should reference request files. Body
    rewrites must provide explicit replacement Markdown, a body file, or a
    request file; do not ask the dry-run tool to infer prose edits.

13. If the user asks for actual edits, make focused changes only after the report
   identifies exact files, risks, and validation commands.

## Proposal kinds

- `remove-redundant-dependency`
- `add-missing-dependency`
- `formulation-impact-review`
- `move-primary-topic`
- `add-topic-membership`
- `merge-duplicate`
- `split-node`
- `generalize-node`
- `mark-lean-topic-divergent`
- `separate-proof-plan-route`
- `write-missing-node-request`
- `needs-human-review`

## Rules

- Agents propose and review; Python validates and projects; admission rules
  decide durable truth.
- Do not write final `graph.json`, topic subgraphs, node payloads, generated
  HTML, or any other generated graph/site artifact.
- Do not silently edit `docs/knowledge/nodes/`.
- Do not move admitted truth into or out of the KB without review evidence.
- Do not resolve mathematical uncertainty by changing node bodies.
- Do not assume graph reachability alone determines whether a descendant is
  affected. Check whether other ancestors' exact formulations preserve, weaken,
  or split the descendant claim.
- Do not run LLM-backed lint unless the user explicitly enables LLM use and a
  budget.
- Distinguish logical `uses` dependencies from expository links. A
  `[[node:id]]` reference is not automatically a `uses` dependency.
- Keep `primary_topic` as ownership and `topics` as browsing membership. Never
  add `uses` merely because two nodes share a topic.
- For duplicate and merge proposals, name the canonical survivor, explain why
  the other node is redundant or narrower, and identify reverse-dependency
  impact.
- For split and generalization proposals, write a request instead of staging or
  admitting mathematical truth directly.
- Do not create request files for node ids already present in the loaded graph
  or staged id index. Staged-node admission or promotion belongs to the
  Admission Referee workflow, not this refactor proposal workflow.
- Keep proof-route `uses` on proof-plan nodes, not on target theorems, unless a
  dependency is also a genuine logical prerequisite of the theorem statement.
- Treat `lean:` as a mechanical link. Semantic alignment requires alignment
  review; Lean module hierarchy mismatch may be intentional and can be handled
  with `topic_lean_alignment: divergent` only when justified.
- Pure lint hygiene should not consume the proposal budget when higher-value
  semantic refactor signals are available. If a major signal is skipped, say so
  in the refinement pass rather than letting it disappear.

## Output locations

- refactor review reports under `docs/knowledge/reviews/`;
- request files under `docs/knowledge/requests/` for new, split, generalized, or
  missing nodes.

## Report format

See `references/refactor-report-schema.md`. For dry-run plans, see
`references/dry-run-plan-schema.md`.
