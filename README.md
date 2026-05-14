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

## The Node Model

Each mathematical object is one Markdown file with YAML frontmatter and a math-only body.

```markdown
---
id: strategic_games.nash_equilibrium
title: Nash Equilibrium
kind: definition
status: admitted
uses:
  - strategic_games.strategic_game
  - strategic_games.strategy_profile
tags:
  - equilibrium
  - solution-concept
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
---

# Nash Equilibrium

A strategy profile $\sigma$ is a Nash equilibrium if no player can improve
their payoff by a unilateral deviation.
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

1. Pick a stable id such as `strategic_games.best_response`.
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
    - GameTheoryLib.StrategicGame.NashEquilibrium
  declarations:
    - StrategicGame.IsNashEquilibrium
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

AI agents are welcome in this repository, but they must preserve the source/build boundary.

Before changing anything, an agent should read:

- [docs/node-format.md](docs/node-format.md)
- [docs/agent-contracts.md](docs/agent-contracts.md)
- [docs/publisher-and-dag.md](docs/publisher-and-dag.md)

### Agents May

- create staged candidate nodes under `docs/knowledge/staged/`;
- write review reports under `docs/knowledge/reviews/`;
- write missing-node or revision requests under `docs/knowledge/requests/`;
- propose Lean code or Lean patches;
- edit admitted nodes only when the human explicitly asks for that exact edit;
- run check, publish, and test commands.

### Agents Must Not

- generate final `graph.json` by hand;
- generate final HTML pages by hand;
- invent final DAG edges or reverse-dependency lists;
- write directly to `docs/knowledge/nodes/` unless explicitly instructed;
- mark a node `admitted`, `formalized`, or `proved` without the required evidence;
- invent dependencies just to make the graph look connected;
- put process notes, reviewer comments, or implementation plans in a node body;
- silently broaden or weaken a mathematical statement;
- treat Lean reference existence as semantic alignment.

### Agent Checklist For Node Work

1. Search existing nodes before creating a new one:

```bash
rg -n "Nash|equilibrium|dominance" docs/knowledge
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
