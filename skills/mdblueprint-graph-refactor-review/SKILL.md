---
name: mdblueprint-graph-refactor-review
description: Use when reviewing an mdblueprint knowledge base for graph-structure refactors, including dependency cleanup, topic taxonomy moves, duplicate or overlap triage, merge/split/generalization proposals, proof-plan route separation, Lean/topic divergence, or impact analysis before editing nodes.
---

# mdblueprint-graph-refactor-review

Review mdblueprint node content and deterministic graph evidence, then propose
bounded refactor actions. This skill is for analysis and proposal writing, not
for automatic admitted-node rewrites.

## Core Rule

Agents propose and review; Python validates and projects; admission rules decide
durable truth. Do not hand-edit generated graph/site artifacts, and do not change
admitted nodes unless the user explicitly asks for edits after seeing the
proposal.

Default durable outputs:

- refactor review reports under `docs/knowledge/reviews/`;
- request files under `docs/knowledge/requests/` for new, split, generalized, or
  missing nodes.

## Evidence Setup

Read these docs before writing proposals:

- `AGENTS.md`
- `docs/agent-contracts.md`
- `docs/node-format.md`
- `docs/topic-model.md`
- `docs/lint.md`
- `docs/publisher-and-dag.md`

Run deterministic checks from the repository root. Prefer the project cache
override when needed:

```bash
uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.check <knowledge-root>
uv --cache-dir /tmp/uv-cache run mdblueprint-lint <knowledge-root> --json
uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.stats <knowledge-root> --json
```

Use `docs/knowledge` unless the user names another knowledge root. For a target
node or topic, build a bounded context bundle:

```bash
uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.context_pack <knowledge-root> --target <node-id>
uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.context_pack <knowledge-root> --topic <topic-id>
```

Add `--include-staged` only when the user asks to consider provisional content,
and mark staged evidence as non-admitted.

## Review Workflow

1. Define scope: whole KB, topic, node, lint finding, or proposed edit.
2. Establish baseline: summarize `check`, relevant `lint` findings, and graph
   stats.
3. Inspect the minimal node set needed: target, direct dependencies, reverse
   dependencies, sibling topic nodes, and staged overlaps when in scope.
4. Classify each candidate action as one of:
   - `mechanical-safe`: deterministic cleanup such as a clearly redundant edge;
   - `semantic-review`: requires mathematical judgment or human confirmation;
   - `request-needed`: requires a `requests/` file before content changes;
   - `blocked`: insufficient evidence or failing baseline checks.
5. Produce a structured report. Use
   `references/refactor-report-schema.md` when writing a durable report.
6. If the user asks for actual edits, make focused changes only after the report
   identifies the exact files and validation plan.

## Proposal Kinds

Use these proposal kinds in reports:

- `remove-redundant-dependency`
- `add-missing-dependency`
- `move-primary-topic`
- `add-topic-membership`
- `merge-duplicate`
- `split-node`
- `generalize-node`
- `mark-lean-topic-divergent`
- `separate-proof-plan-route`
- `write-missing-node-request`
- `needs-human-review`

## Review Criteria

Dependency proposals must distinguish logical prerequisites from expository
links. A `[[node:id]]` reference is not automatically a `uses` dependency.

Topic proposals must keep `primary_topic` as ownership and `topics` as browsing
membership. Never add `uses` merely because two nodes share a topic.

Duplicate and merge proposals must name the canonical survivor, explain why the
other node is redundant or narrower, and identify reverse-dependency impact.

Split and generalization proposals must write a request instead of staging or
admitting mathematical truth directly.

Proof-plan proposals must keep proof-route `uses` on the proof plan, not on the
target theorem, unless a dependency is also a genuine logical prerequisite of
the theorem statement.

Lean-aware proposals must treat `lean:` as a mechanical link. Semantic alignment
requires alignment review; Lean module hierarchy mismatch may be intentional and
can be handled with `topic_lean_alignment: divergent` only when justified.

## Output Rules

For conversational answers, cite node ids and file paths. For durable outputs,
write a review report under `docs/knowledge/reviews/` with a machine-readable
header and proposal table.

For new-node, split-node, generalize-node, missing-dependency, or Lean-bridge
actions, write a request file under `docs/knowledge/requests/` using the schema
in `docs/node-format.md`.

Do not:

- write final `graph.json`, topic subgraphs, node payloads, or generated HTML;
- silently edit `docs/knowledge/nodes/`;
- move admitted truth into or out of the KB without review evidence;
- resolve mathematical uncertainty by changing node bodies;
- run LLM-backed lint unless the user explicitly enables LLM use and a budget.
