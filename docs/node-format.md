# Node Format

Each node is one Markdown file. The YAML frontmatter stores system information. The Markdown body stores only mathematics.

## Example

```markdown
---
id: topology.metric_space.complete
title: Complete Metric Space
kind: definition
status: admitted
uses:
  - topology.metric_space.cauchy_sequence
lean:
  modules:
    - MyLibrary.Topology.MetricSpace
  declarations:
    - MetricSpace.Complete
source:
  artifacts:
    - id: topology-text
      path: references/topology-text.pdf
  spans:
    - artifact: topology-text
      locator: "Chapter 2, page 45"
      format: book-page
      note: "Definition of complete metric space"
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary metric spaces?"
  verdict: "Yes, no finiteness or separability assumption is imposed."
tags:
  - topology
  - metric-space
---

# Complete Metric Space

A metric space $(X, d)$ is complete if every Cauchy sequence in $X$ converges
to a point of $X$.
```

## Source Format

The `source` field records where the mathematical content came from.

```yaml
source:
  artifacts:
    - id: <short-identifier>
      path: <relative path under docs/knowledge/sources/ or references/>
  spans:
    - artifact: <artifact id>
      locator: <locator string>
      format: <locator format>
      note: <optional human note>
```

Each span must name the `artifact` it comes from. When there is only one artifact,
the `artifact` field may be omitted and the span is bound to that artifact implicitly.

Valid `format` values:

```text
book-page      — "Chapter N, page M" or "page M"
section        — "Section N.M" or "Theorem N.M.K" with number
arxiv-theorem  — "Theorem N" in an arXiv preprint with arxiv id in the artifact path
lean-location  — "Module.Name:line" or just a declaration name
url            — a fragment identifier or section anchor
```

If the format is unknown or the source is informal, omit `format` and explain in `note`.

## Verification Fields

The `verification` block uses only the fields that apply to the node's `kind`.

| Field       | Applies to                                               | Values                                  |
|-------------|----------------------------------------------------------|-----------------------------------------|
| `statement` | lemma, proposition, theorem, external-theorem            | accepted, needs_revision, rejected      |
| `definition`| definition, concept                                      | accepted, needs_revision, rejected      |
| `proof`     | lemma, proposition, theorem (when proof content exists)  | accepted, gap, critical, not_applicable |
| `alignment` | any node with a `lean` section                           | aligned, pending, mismatch              |

A node should not carry both `statement` and `definition`. Use the field that matches
the kind. Use `not_applicable` for `proof` only when the node kind cannot have a proof
(e.g. a pure definition, a concept, an example).

## Body Rule

The body must not contain operational sections such as:

- status;
- implementation notes;
- Lean interface;
- task checklist;
- agent discussion;
- reviewer metadata.

Those belong in YAML, `reviews/`, or `requests/`.

## Node Kinds

The first version supports:

```text
concept
definition
lemma
proposition
theorem
example
proof-plan
external-theorem
task
```

`task` nodes track mathematical work items (e.g. "prove X", "formalize Y"). They may
appear in the `uses` field of other `task` nodes to express project dependency order.
Mathematical content nodes (definition, lemma, theorem, etc.) must not reference `task`
nodes in their `uses` field. A `task` node's `uses` field lists only other `task` nodes
or mathematical nodes that the task depends on for context, but not as a logical
mathematical dependency. Routine project management items should not be in the node body.

## Status Model

Use a small status vocabulary:

```text
staged
needs_statement_review
needs_definition_review
needs_proof_review
admitted
formalized
proved
blocked
deprecated
```

Only files under `docs/knowledge/nodes/` should normally have `admitted`, `formalized`, or `proved` status.

Files under `docs/knowledge/staged/` are proposals even if their YAML says the mathematical content looks plausible.

## Staged Node Schema

Staged nodes use the same YAML frontmatter structure as admitted nodes, but with
a relaxed required-field set. The Python validator applies a staged profile when
`status` is `staged` or any `needs_*` value.

Required fields for staged nodes:

```text
id        — must be unique; use a provisional topic prefix
title
kind
status    — must be staged or needs_statement_review / needs_definition_review /
            needs_proof_review
```

Optional for staged nodes (required before admission):

```text
uses          — list known dependencies; leave empty rather than inventing
source        — include if extractable from the source material
verification  — omit or leave fields as pending
generality    — omit if not yet reviewed
lean          — omit if no Lean link exists yet
```

Staged nodes must not have `status: admitted`, `status: formalized`, or
`status: proved`. The schema validator rejects staged files in `docs/knowledge/staged/`
that carry any of those three status values.

## Requests Format

Files under `docs/knowledge/requests/` use the following schema:

```yaml
request_id: <unique string, e.g. req-2026-001>
kind: new-node | split-node | generalize-node | missing-dependency | lean-bridge
requested_by: <agent name from agent-contracts>
created_at: "ISO-8601 timestamp"
target_kind: <node kind of the requested node>
proposed_id: <candidate stable id>
proposed_title: <one-line title>
summary: <one sentence explaining what is requested>
reason: |
  Why existing nodes are insufficient.
proposed_statement: |
  The most general useful form of the proposed content.
proposed_uses:
  - <node ids this new node would depend on>
source_justification: |
  Source or mathematical justification for this content being a reusable node
  rather than a local Lean lemma or inline remark.
```

A request file must not contain admitted mathematical truth. It is a proposal awaiting
human or referee decision.

## Required Structural Checks

Deterministic Python tools should fail with clear diagnostics for:

- missing required YAML fields (using admitted or staged profile as appropriate);
- invalid status or kind;
- duplicate node ids;
- missing dependencies (for admitted nodes; warn for staged);
- dependency cycles;
- mathematical nodes referencing `task` nodes in `uses`;
- malformed Lean references;
- `source.spans` entries whose `artifact` id does not appear in `source.artifacts`;
- node body containing forbidden operational headings;
- staged nodes in `docs/knowledge/nodes/` (wrong directory);
- admitted nodes in `docs/knowledge/staged/` (wrong status);
- generated graph output not matching parsed nodes.
