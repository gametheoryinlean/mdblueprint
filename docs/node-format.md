# Node Format

Each node is one Markdown file. The YAML frontmatter stores system information. The Markdown body stores only mathematics.

## Example

```markdown
---
id: topology.metric_space.complete
title: Complete Metric Space
kind: definition
status: admitted
primary_topic: topology.metric_spaces
topics:
  - topology.metric_spaces
uses:
  - topology.metric_space.cauchy_sequence
lean:
  repository: topology
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

## Topic Fields

Topic fields separate file ownership from graph browsing views. See
[topic-model.md](topic-model.md) for the full contract.

```yaml
primary_topic: topology.metric_spaces
topics:
  - topology.metric_spaces
  - analysis.cauchy_sequences
```

Field contract:

- `primary_topic` is the node's home topic. It is a canonical topic id, not an
  alias, and determines the default owner and ordinary file placement.
- `topics` lists every topic view that should include the node in topic pages
  and topic DAG projections.
- `primary_topic` must appear in `topics`.
- A node may have several `topics`, but it has only one `primary_topic`.
- `uses` remains only the logical dependency list. Do not add a dependency just
  because two nodes share a topic.
- `tags` remain keyword/search metadata. Do not use tags as a substitute for
  topic membership.

Older nodes may omit these fields while tooling falls back to deriving a topic
from the node id. New or edited nodes should use explicit topic fields.

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

## Lean Reference Format

The `lean` field records mechanical links from a Markdown node to Lean declarations.

```yaml
lean:
  repository: core
  modules:
    - Example.Basic
  declarations:
    - Example.basic_identity
```

Field contract:

- `repository` is the id of a configured Lean repository from
  `docs/knowledge/mdblueprint.yml`. It may be omitted only when the project config
  has `lean.default_repository`.
- `modules` is a list of Lean module names expected to exist under the selected
  repository root.
- `declarations` is a list of Lean declaration names expected to exist in the
  selected repository.
- Fully qualified declaration names are preferred. Short names are accepted only
  when they match exactly one indexed declaration by suffix.
- An `external-theorem` node must include both `lean.modules` and
  `lean.declarations`.
- A Lean reference proves existence of a Lean object, not semantic alignment with
  the Markdown statement. Use `verification.alignment` and alignment review reports
  for that claim.

See [lean-repositories.md](lean-repositories.md) for repository config, source URL
templates, diagnostics, and publishing behavior.

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

## Math Body Format

Node bodies may use Markdown prose plus TeX math. Preferred math delimiters are
`\(...\)` for inline math and `\[...\]` for display math. Dollar delimiters are
enabled for compatibility, but new nodes should prefer the backslash-delimited forms.

Reusable macros must be declared in project config under `math.macros`; do not put
`\newcommand` or TeX preamble commands in the node body. Display environments such
as `aligned` or `cases` must be wrapped in display delimiters.

Run static math diagnostics before publishing:

```bash
uv run python -m tools.knowledge.check docs/knowledge
```

After publishing, run browser-level KaTeX verification:

```bash
uv run --extra browser python -m tools.knowledge.render_check /tmp/mdblueprint-site
```

See [math-authoring.md](math-authoring.md) for the full delimiter, macro, Markdown
interaction, and render-check contract.

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

`proof-plan` nodes describe candidate proof routes for a theorem-like node. They
must use `target` to name the theorem, lemma, proposition, or external theorem they
are trying to prove. Their `uses` list records dependencies of that proof route,
not extra logical dependencies of the target theorem.

```yaml
id: algebra.group_identity_unique.plan.via_left_cancel
title: Group Identity Is Unique via Left Cancellation
kind: proof-plan
status: staged
target: algebra.group_identity_unique
plan_status: candidate
uses:
  - algebra.group
```

Valid `plan_status` values are:

```text
candidate
selected
rejected
blocked
formalized
```

The dependency graph treats proof plans with typed edges:

```text
theorem --has_plan--> proof-plan
proof-plan --uses--> lemma-or-definition
```

Do not put a proof-plan id in a theorem's `uses` list. This keeps the main
mathematical dependency DAG separate from alternative proof routes. A proof plan
also must not put its own `target` in `uses`; the `target` relation is represented
by the typed `has_plan` edge.

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

`admitted` means the Markdown node has passed the mathematical admission gates.
It does not require a Lean link. `formalized` and `proved` are stronger claims
about Lean coverage and must include both `lean.modules` and
`lean.declarations`.

## Staged Node Schema

Staged nodes use the same YAML frontmatter structure as admitted nodes, but with
a relaxed required-field set. The Python validator applies a staged profile when
`status` is `staged` or any `needs_*` value.

Required fields for staged nodes:

```text
id        — must be unique; keep stable even when topic memberships change
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

Before a staged node can move into `docs/knowledge/nodes/`, run the deterministic
admission pipeline:

```bash
uv run python -m tools.knowledge.admission_pipeline docs/knowledge/staged/example.md docs/knowledge
```

The pipeline applies these gates in order:

```text
schema -> generality -> verification -> reviews -> dag -> write
```

The verification gate is kind-specific:

```text
concept, definition              require verification.definition: accepted
lemma, proposition, theorem      require verification.statement: accepted
external-theorem                 requires verification.statement: accepted and Lean refs
proof block in any theorem-like  requires verification.proof: accepted
```

Lean remains optional for ordinary admitted Markdown nodes. Lean evidence becomes
mandatory only when the node status is `formalized` or `proved`, or when the kind
is `external-theorem`.

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
