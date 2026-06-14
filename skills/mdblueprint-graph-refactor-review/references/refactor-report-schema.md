# Refactor Report Schema

Use this schema for durable graph-refactor review reports under
`docs/knowledge/reviews/`.

Validate a completed report before treating its proposals as actionable:

```bash
uv run python -m tools.knowledge.refactor_report_check docs/knowledge <report-path>
```

```yaml
agent: graph-refactor-proposer
target:
  knowledge_root: <path to knowledge root>
  node_id: <optional node id>
  topic: <optional topic id>
decision: proposals | no_action | needs_human_decision | blocked
created_at: "ISO-8601 timestamp"
inputs:
  - <command output, node file, lint finding, or context bundle>
summary: <one sentence>
baseline:
  check: passed | failed | not_run
  lint: passed | findings | not_run
  stats: collected | not_run
formulation_impact:
  reviewed: true | false
  reason: <why formulation-sensitive analysis was or was not needed>
```

The Markdown body should contain these sections.

## Scope

State whether the report covers the whole knowledge base, one topic, one node,
or a selected set of lint findings. Say whether staged nodes were included.

## Deterministic Baseline

Summarize relevant command results:

- structural check status;
- lint finding codes and counts;
- graph stats that affect the recommendation, such as hot spots, orphans,
  depth, or topic counts.

## Proposals

Use one table row per proposal.

| Field | Meaning |
| --- | --- |
| `proposal_id` | Stable local id such as `refactor-001`. |
| `kind` | One of the proposal kinds in `SKILL.md`. |
| `classification` | `mechanical-safe`, `semantic-review`, `request-needed`, or `blocked`. |
| `targets` | Node ids, topic ids, request files, or lint finding codes. |
| `action` | Exact proposed change or request to write. |
| `evidence` | Node ids, file paths, lint findings, or graph facts supporting the action. |
| `risk` | What could be wrong if the proposal is accepted. |
| `validation` | Commands to run after applying the proposal. |

## Generality Gate

For proposals that generalize, split, merge, or rehome mathematical content,
record the gate explicitly:

- most general useful form;
- whether the current node already has that form;
- whether a narrower form is deliberate;
- assumptions that might be removable;
- hypotheses that may be artifacts of the current source or topic placement.

If the answer is unclear, mark the proposal `semantic-review` or
`needs-human-review`.

## Formulation-Sensitive Impact

For proposals that modify, weaken, strengthen, replace, or delete a node or
dependency, include the analysis from `formulation-impact.md`:

- descendants reviewed;
- role of the changed item;
- other ancestor formulations that may preserve descendant claims;
- affected status for each important descendant;
- bridge, split, or generalization requests needed.

## Request Files

If a proposal requires a `docs/knowledge/requests/` file, include the intended
request kind and fields. Do not state unreviewed mathematical truth as admitted
fact.

## Human Decisions

List choices that require a human or admission referee, especially canonical
node selection, semantic merge decisions, topic taxonomy policy, and intentional
Lean/topic divergence.
