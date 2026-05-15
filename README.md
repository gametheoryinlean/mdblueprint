# mdblueprint

`mdblueprint` is a Markdown-first blueprint system for mathematical knowledge bases that are meant to work with Lean. It keeps small Markdown files as the durable source of truth, then uses deterministic Python tools to validate the dependency graph, check mechanical Lean references, export machine-readable graph data, and publish a leanblueprint-style static site.

It does not use LaTeX, plasTeX, or leanblueprint as the source pipeline. The project borrows the useful presentation style of leanblueprint while keeping the source model simple enough for humans and AI agents to edit safely.

## What This Tool Owns

`mdblueprint` separates mathematical source, deterministic build products, and AI assistance:

```text
Durable source:
  docs/knowledge/nodes/**/*.md      admitted mathematical nodes
  docs/knowledge/staged/**/*.md     candidate nodes under review
  docs/knowledge/reviews/**/*.md    verifier and referee reports
  docs/knowledge/requests/**/*.md   requests for missing or revised nodes

Deterministic Python output:
  graph.json
  topic pages
  keyword pages
  node pages
  dep_graph_document.html / graph.html

AI-assisted output:
  staged candidate nodes
  review reports
  Lean proposals
  alignment reports
  requests for missing nodes
```

Python tools, not LLMs, generate the final graph, reverse dependencies, HTML pages, and static-site index pages.

## Install

Use Python 3.10 or newer.

```bash
uv sync --extra dev
```

If you are not using `uv`, install the package in editable mode and install the development dependencies from `pyproject.toml`.

```bash
pip install -e '.[dev]'
```

## Quickstart For Humans

Validate the example knowledge base:

```bash
uv run python -m tools.knowledge.check docs/knowledge
```

Publish the static site to a temporary directory:

```bash
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

Preview the generated site locally:

```bash
python -m http.server 8001 --directory /tmp/mdblueprint-site
```

Then open:

```text
http://127.0.0.1:8001/index.html
```

Run the full test suite:

```bash
uv run --extra dev python -m pytest -q
```

## Command Reference

Call the tools as Python modules from the repository root.

```bash
# Structural checks for nodes, staged candidates, dependencies, and cycles
uv run python -m tools.knowledge.check docs/knowledge

# Add mechanical Lean reference prechecks
uv run python -m tools.knowledge.check docs/knowledge --lean-root path/to/lean/project

# Generate graph.json and the static HTML site
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site

# Index Lean declarations from a Lean project
uv run python -m tools.knowledge.lean_index path/to/lean/project

# Admit a staged node after review gates pass
uv run python -m tools.knowledge.admit docs/knowledge/staged/example.md docs/knowledge
```

The publisher refuses to delete the knowledge source tree. For local previews, prefer publishing to `/tmp/...` or another build directory outside `docs/knowledge`.

## Project Layout

```text
tools/knowledge/
  models.py          node, source, Lean, verification dataclasses
  parser.py          YAML frontmatter and Markdown body parser
  validator.py       schema validation for admitted and staged nodes
  graph.py           dependency DAG builder with cycle detection
  export.py          deterministic graph.json export
  check.py           structural checker CLI
  blueprint_view.py  leanblueprint-style presentation model and DOT export
  publish.py         static-site publisher
  lean_index.py      Lean declaration indexer
  lean_check.py      mechanical Lean reference prechecks
  admit.py           staged-to-admitted workflow
  templates/         generated-site HTML, CSS, and graph JS

docs/
  architecture.md
  node-format.md
  agent-contracts.md
  publisher-and-dag.md
  reference-repos.md
  skills.md

docs/knowledge/
  nodes/             admitted Markdown nodes
  staged/            candidate Markdown nodes
  reviews/           verifier/referee reports
  requests/          proposed missing or revised nodes
```

## Using Skills

The repo includes workflow skills under [`skills/`](skills/) for humans and AI agents. They are the recommended entry points for recurring mdblueprint tasks.

| Task | Skill |
| --- | --- |
| Extract theorems, definitions, examples, or proof ideas from a book, PDF, paper, TeX source, or notes | `mdblueprint-source-extraction` |
| Create or edit a Markdown knowledge node by hand | `mdblueprint-node-author` |
| Review staged nodes before admission | `mdblueprint-node-review` |
| Generate Lean declarations or proof skeletons from admitted nodes | `mdblueprint-lean-generation` |
| Check semantic alignment between Markdown and Lean | `mdblueprint-alignment-review` |
| Publish or inspect the generated site and dependency graph | `mdblueprint-publish` |

If your assistant does not auto-discover repo-local skills, open the relevant `skills/<name>/SKILL.md` and follow it manually. See [skills/README.md](skills/README.md) and [docs/skills.md](docs/skills.md) for Claude Code and Codex installation notes.

## The Node Model

Each mathematical object is one Markdown file with YAML frontmatter and a math-only body.

```markdown
---
id: algebra.groups.group
title: Group
kind: definition
status: admitted
uses:
  - algebra.sets.binary_operation
tags:
  - algebra
  - group-theory
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
---

# Group

A group is a set $G$ with a binary operation $\cdot$, an identity element
$e$, and inverses, such that the operation is associative.
```

Important rules:

- `id` is stable machine identity. It determines topic grouping and generated filenames.
- `title` is the human-facing label used in the generated site.
- `kind` controls theorem/definition styling and validation.
- `status` records the workflow state.
- `uses` lists logical dependencies by node id.
- `tags` generate keyword pages.
- The Markdown body should contain mathematics only, not process notes.

Read [docs/node-format.md](docs/node-format.md) before creating or editing nodes.

## Valid Kinds And Statuses

Supported node kinds:

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

Supported statuses:

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

Files under `docs/knowledge/nodes/` should normally use `admitted`, `formalized`, or `proved`. Files under `docs/knowledge/staged/` should use `staged` or a `needs_*` status.

## Human Workflow

### 1. Add Or Edit An Admitted Node

Use this only when you are directly maintaining trusted source files.

1. Pick a stable id such as `algebra.groups.group_homomorphism`.
2. Put the file under `docs/knowledge/nodes/<topic>/`.
3. Write YAML frontmatter according to [docs/node-format.md](docs/node-format.md).
4. Keep the body mathematical. Do not add operational headings like "Status", "Implementation notes", or "Agent discussion".
5. Run:

```bash
uv run python -m tools.knowledge.check docs/knowledge
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

### 2. Draft A Candidate Node

Use this for extracted, uncertain, or AI-proposed material.

1. Put the file under `docs/knowledge/staged/`.
2. Use `status: staged` or one of the `needs_*` statuses.
3. Include source spans when available.
4. Leave `uses: []` if dependencies are unknown; do not invent dependencies.
5. Add review reports under `docs/knowledge/reviews/`.
6. When review gates pass, run:

```bash
uv run python -m tools.knowledge.admit docs/knowledge/staged/example.md docs/knowledge
```

Admission checks staged schema, generality review, review evidence, and DAG validity before moving the node into `docs/knowledge/nodes/`.

### 3. Connect A Node To Lean

Add a `lean` block when a node corresponds to Lean declarations:

```yaml
lean:
  modules:
    - MyLibrary.Algebra.Groups
  declarations:
    - Algebra.Group
```

Then run:

```bash
uv run python -m tools.knowledge.check docs/knowledge --lean-root path/to/lean/project
```

The Lean precheck is mechanical. It checks that modules and declarations exist and reports obvious `sorry` or `admit` markers. It does not prove semantic alignment between Markdown and Lean.

### 4. Publish The Website

```bash
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

The generated site includes:

- `index.html`: title-first topic outline
- `<topic>/index.html`: topic pages
- `keywords/<tag>.html`: tag-based keyword pages
- `<topic>/<node_id>.html`: node pages with theorem/definition wrappers
- `dep_graph_document.html`: Graphviz dependency graph with modals
- `graph.html`: compatibility alias for the dependency graph
- `graph.json`: deterministic machine graph export

Proof text is collapsed by default when the body contains a recognized proof marker:

```text
*Proof.*
**Proof.**
Proof.
## Proof
```

The source file remains plain Markdown; proof folding is a presentation-layer feature.

## AI And Agent Instructions

AI agents are welcome in this repository, but they must preserve the source/build boundary. The authoritative, detailed version is [docs/agent-contracts.md](docs/agent-contracts.md). This README repeats the operational contract so an agent can start safely from this file alone.

Before changing anything, an agent should read:

- [docs/node-format.md](docs/node-format.md)
- [docs/agent-contracts.md](docs/agent-contracts.md)
- [docs/publisher-and-dag.md](docs/publisher-and-dag.md)

### Universal Agent Contract

Every agent must state or infer these fields before it writes files:

- role: one of the contracts below;
- inputs: exact files, source excerpts, Lean modules, or command outputs used;
- outputs: exact files to write or patches to propose;
- allowed write locations;
- forbidden write locations;
- decision vocabulary;
- uncertainty behavior;
- whether it may propose new nodes.

Every report-like output must start with machine-readable metadata:

```yaml
agent: source-to-md | statement-verifier | proof-verifier | lean-generator | alignment-verifier | admission-referee
target:
  node_id: optional.node.id
  path: docs/knowledge/staged/example.md
decision: one value from this agent's decision vocabulary
created_at: "ISO-8601 timestamp"
inputs:
  - path/or/source/identifier
summary: one short sentence
```

The report body may explain reasoning in prose, but the `decision` field must remain machine-readable.

### Global Permissions

- create staged candidate nodes under `docs/knowledge/staged/`;
- write review reports under `docs/knowledge/reviews/`;
- write missing-node or revision requests under `docs/knowledge/requests/`;
- propose Lean code or Lean patches;
- edit admitted nodes only when the human explicitly asks for that exact edit;
- run check, publish, and test commands.

### Global Prohibitions

- generate final `graph.json` by hand;
- generate final HTML pages by hand;
- invent final DAG edges or reverse-dependency lists;
- write directly to `docs/knowledge/nodes/` unless explicitly instructed;
- mark a node `admitted`, `formalized`, or `proved` without the required evidence;
- invent dependencies just to make the graph look connected;
- put process notes, reviewer comments, or implementation plans in a node body;
- silently broaden or weaken a mathematical statement;
- treat Lean reference existence as semantic alignment.

### Source-to-MD Contract

Purpose: convert PDFs, books, papers, TeX, or notes into staged Markdown candidate nodes.

Inputs:

- source files or source excerpts;
- source manifest or citation information;
- target topic directory;
- existing admitted and staged node index.

Allowed writes:

- `docs/knowledge/staged/**/*.md`;
- uncertainty or extraction notes under `docs/knowledge/reviews/`.

Forbidden writes:

- `docs/knowledge/nodes/**`;
- generated site files;
- `graph.json`.

Decision vocabulary:

```text
extracted
partial
uncertain
blocked
```

Rules:

- search existing nodes before creating a candidate;
- preserve source locators in `source.artifacts` and `source.spans`;
- extract one reusable mathematical object per node;
- use `status: staged` or a `needs_*` status;
- do not invent dependencies beyond source evidence or existing node ids;
- if the source statement is narrower than the likely reusable form, keep the source-local claim and ask the generality question in a report.

May propose new nodes: yes, but only as staged candidates with source locators.

### Statement Or Definition Verifier Contract

Purpose: check that a staged or admitted statement/definition is mathematically correct, well-scoped, and general enough.

Inputs:

- target node;
- dependencies named by `uses`;
- source spans when available;
- project notation conventions when available.

Allowed writes:

- review reports under `docs/knowledge/reviews/`;
- optional revision or missing-dependency requests under `docs/knowledge/requests/`.

Forbidden writes:

- admitted nodes;
- generated site files;
- final graph artifacts.

Decision vocabulary:

```text
accepted
needs_revision
rejected
```

Rules:

- verify assumptions, notation, dependency adequacy, and generality;
- ask: "What is the most general useful form of this statement, and is the current form acceptable?";
- do not silently rewrite admitted truth;
- if a dependency is missing or a statement should be split, write a request rather than directly creating admitted content.

May propose new nodes: only through `docs/knowledge/requests/`.

### Proof Verifier Contract

Purpose: check that proof text or a proof sketch proves the stated result.

Inputs:

- node statement;
- proof body or proof sketch;
- dependencies named by `uses`;
- relevant source spans or Lean declarations if available.

Allowed writes:

- proof review reports under `docs/knowledge/reviews/`;
- optional missing-lemma requests under `docs/knowledge/requests/`.

Forbidden writes:

- admitted nodes;
- generated graph or site files;
- silent proof repairs without a report.

Decision vocabulary:

```text
accepted
gap
critical
```

Rules:

- identify exact gaps, hidden assumptions, circular reasoning, or misuse of prior nodes;
- distinguish a local proof gap from a reusable missing lemma;
- write a request for a reusable missing lemma instead of inserting it as admitted truth.

May propose new nodes: only through `docs/knowledge/requests/`.

### MD-to-Lean Generator Contract

Purpose: generate Lean declarations, proof skeletons, or Lean patch proposals from admitted Markdown nodes.

Inputs:

- admitted target node;
- dependency nodes;
- Lean declaration index;
- existing Lean modules.

Allowed writes:

- Lean patch proposals or generated Lean files when the human asks for code work;
- `docs/knowledge/requests/` for missing auxiliary mathematical nodes;
- optional review notes explaining formalization choices.

Forbidden writes:

- admitted Markdown nodes without a human request;
- final graph or site files;
- weakened Markdown statements without a review note.

Decision vocabulary:

```text
generated
blocked_by_missing_node
blocked_by_missing_definition
blocked_by_lean_error
request_human
```

Rules:

- generate Lean against admitted Markdown, not staged truth;
- preserve the mathematical statement unless a report explicitly explains the mismatch;
- propose auxiliary mathematical content only through `docs/knowledge/requests/`;
- explain why a proposed auxiliary result should be a reusable node rather than a local Lean lemma.

May propose new nodes: yes, only through `docs/knowledge/requests/`.

### External-Theorem Admission Contract

Purpose: admit a Markdown node for a theorem already proved in Lean, such as Mathlib or another Lean library result.

Inputs:

- Lean module and declaration names;
- Markdown statement;
- source or Lean locator;
- alignment review evidence.

Allowed writes:

- admitted `external-theorem` node only when the workflow explicitly chooses the external-theorem direct-admission path;
- alignment and admission reports under `docs/knowledge/reviews/`.

Forbidden writes:

- generated graph or site files;
- external-theorem nodes without Lean module and declaration references.

Decision vocabulary:

```text
admit_external
needs_alignment
needs_statement_review
needs_human_decision
reject
```

Required node fields:

- `kind: external-theorem`;
- `lean.modules`;
- `lean.declarations`;
- `verification.statement`;
- `verification.alignment`;
- completed `generality` gate.

Required checks:

- `lean.modules` and `lean.declarations` exist mechanically;
- statement verifier decision is `accepted`;
- alignment verifier decision is `aligned` or an explicitly acceptable `lean_stronger`;
- no proof verifier is required when the proof already exists in Lean.

Forbidden behavior:

- do not use external theorem admission to bypass statement review;
- do not claim semantic alignment from declaration existence alone.

### MD-Lean Alignment Verifier Contract

Purpose: decide whether a Lean declaration semantically matches a Markdown node.

Inputs:

- Markdown node and dependencies;
- Lean module and declaration references;
- Lean declaration index or signatures;
- mechanical precheck output.

Allowed writes:

- alignment reports under `docs/knowledge/reviews/`.

Forbidden writes:

- final status updates;
- admitted node rewrites;
- generated graph or site files.

Decision vocabulary:

```text
aligned
lean_stronger
lean_weaker
lean_special_case
lean_extra_hypotheses
lean_missing_hypotheses
definition_mismatch
uncertain
```

Rules:

- run or consume deterministic Lean reference prechecks first;
- report extra hypotheses, missing hypotheses, weaker conclusions, stronger conclusions, specialization, or definition mismatch;
- do not treat Python prechecks as semantic proof;
- return an alignment report, not an automatic truth update.

May propose new nodes: no. It may request human review when a mismatch reveals missing mathematical content.

### Admission Referee Contract

Purpose: decide whether a staged node and its evidence justify admission.

Inputs:

- staged candidate node;
- statement or definition verifier report;
- proof verifier report when proof content exists;
- generality gate answer;
- deterministic Python check report.

Allowed writes:

- admission report under `docs/knowledge/reviews/`;
- controlled move into `docs/knowledge/nodes/` only when the workflow explicitly approves admission.

Forbidden writes:

- direct mathematical rewriting without a report;
- admission when dependencies are missing or cyclic;
- admission without a completed generality gate;
- silent resolution of conflicting reports.

Decision vocabulary:

```text
admit
needs_revision
needs_human_decision
reject
```

Rules:

- if reports disagree, return `needs_human_decision`;
- if checks fail, return `needs_revision` or `reject`;
- when approved, use the admission workflow rather than manually copying files:

```bash
uv run python -m tools.knowledge.admit docs/knowledge/staged/example.md docs/knowledge
```

May propose new nodes: no.

### Request File Contract

Any agent that wants new mathematical content but is not allowed to create an admitted node must write a request under `docs/knowledge/requests/`.

Required shape:

```yaml
request_id: req-2026-001
kind: new-node | split-node | generalize-node | missing-dependency | lean-bridge
requested_by: <agent name>
created_at: "ISO-8601 timestamp"
target_kind: <node kind>
proposed_id: <candidate stable id>
proposed_title: <one-line title>
summary: <one sentence>
reason: |
  Why existing nodes are insufficient.
proposed_statement: |
  The most general useful form of the proposed content.
proposed_uses:
  - existing.node.id
source_justification: |
  Source or mathematical reason this should be a reusable node.
```

Request files are proposals. They are not admitted mathematical truth.

### Agent Checklist For Node Work

1. Search existing nodes before creating a new one:

```bash
rg -n "<keyword>|<alternate term>" docs/knowledge
```

2. Choose one node per reusable mathematical object.
3. Keep machine metadata in YAML and mathematics in the Markdown body.
4. Use `docs/knowledge/staged/` for uncertain or extracted content.
5. Put disagreements, gaps, and uncertainty in `reviews/` or `requests/`.
6. Run structural checks after edits:

```bash
uv run python -m tools.knowledge.check docs/knowledge
```

7. If the generated site matters, publish and inspect:

```bash
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

8. If code changed, run tests:

```bash
uv run --extra dev python -m pytest -q
```

## Deterministic Boundary

This project relies on a strict boundary:

```text
LLMs can propose and review.
Python decides structure.
Humans admit mathematical truth.
```

That means:

- A staged node is not admitted truth.
- A review report is evidence, not an automatic merge.
- `graph.json` and HTML output are generated artifacts.
- Stable ids may appear in URLs, anchors, and machine data, but generated UI should prefer titles.
- Dependency graph display uses `dependency -> dependent`, even though internal graph edges store `dependent -> dependency`.

## Verification Before Committing

For documentation-only changes:

```bash
uv run --extra dev python -m pytest -q
git diff --check
```

For generic documentation, skills, or tooling changes, also run the domain-neutrality audit:

```bash
uv run --extra dev python -m pytest tests/test_domain_neutrality.py -q
```

This audit allows domain fixtures only under `docs/knowledge/**` and `tests/fixtures/**`.

For node or publisher changes:

```bash
uv run python -m tools.knowledge.check docs/knowledge
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
uv run --extra dev python -m pytest -q
git diff --check
```

For Lean-linked changes:

```bash
uv run python -m tools.knowledge.check docs/knowledge --lean-root path/to/lean/project
```

## Troubleshooting

`missing dependency`

: A node lists a `uses` id that does not exist. Search existing nodes, fix the id, or create a staged request for the missing dependency.

`dependency cycle`

: The `uses` relation is circular. Split statements or remove an incorrect dependency.

`node in staged/ has admitted status`

: Staged files must use `staged` or `needs_*` statuses. Admission is a separate workflow.

`forbidden operational heading in body`

: Move process notes into YAML, `reviews/`, or `requests/`. Node bodies are for mathematics only.

`external-theorem must have lean.modules and lean.declarations filled`

: External theorem nodes must point to existing Lean modules and declarations.

## Current Status

The core implementation phases are complete:

1. Deterministic parser, validator, DAG, `graph.json`, and static site
2. Lean declaration indexing and mechanical reference prechecks
3. Agent contracts and report schemas
4. Staged-to-admitted workflow with review and generality gates
5. Leanblueprint-style publisher with title-first navigation, keyword pages, theorem wrappers, proof folding, and Graphviz dependency views

The test suite is the source of truth for current coverage.
