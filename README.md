# mdblueprint

`mdblueprint` is a Markdown-first blueprint system for mathematical knowledge bases that are meant to work with Lean, without making `leanblueprint` or TeX blueprint files the source of truth.

The durable source is a directory of small Markdown nodes:

```text
docs/knowledge/nodes/**/*.md
```

Python tools parse those nodes, validate the dependency DAG, check mechanical Lean references, and generate a leanblueprint-style static website. The publisher keeps Markdown nodes as the durable source and emits a title-first topic outline, keyword pages, theorem/definition wrappers, collapsed proof sections, Uses and Lean declaration modals, and a Graphviz-style dependency graph. It does not use LaTeX, plasTeX, or leanblueprint as the source pipeline.

LLM agents may extract candidate nodes, review statements and proofs, generate Lean proposals, and judge semantic MD-Lean alignment, but they do not generate the final DAG or website.

## Core Boundary

```text
LLM agents:
  source -> staged Markdown candidates
  node -> statement/definition/proof review reports
  admitted node -> Lean proposal
  Markdown + Lean -> semantic alignment report

Python tools:
  Markdown -> schema validation
  Markdown -> dependency DAG
  Markdown + Lean index -> mechanical prechecks
  Markdown -> graph.json and static HTML
```

## Design Docs

- [Architecture](docs/architecture.md)
- [Node Format](docs/node-format.md)
- [Agent Contracts](docs/agent-contracts.md)
- [Skill Design](docs/skills.md)
- [Publisher and DAG](docs/publisher-and-dag.md)
- [Reference Repositories](docs/reference-repos.md)

## Quickstart

```bash
# Install
uv sync          # or: pip install -e .

# Validate the knowledge base
python -m tools.knowledge.check docs/knowledge

# Validate with Lean reference prechecks
python -m tools.knowledge.check docs/knowledge --lean-root path/to/lean/project

# Generate the static site
python -m tools.knowledge.publish docs/knowledge

# Index Lean declarations
python -m tools.knowledge.lean_index path/to/lean/project

# Admit a staged node
python -m tools.knowledge.admit docs/knowledge/staged/node.md docs/knowledge

# Run tests
uv run --with pytest --with pytest-cov python -m pytest --cov=tools
```

## Project Structure

```text
tools/knowledge/
  models.py       # Node, LeanRef, Source, Verification dataclasses
  parser.py       # YAML frontmatter + Markdown body parser
  validator.py    # Schema validation (admitted and staged profiles)
  graph.py        # DAG builder with cycle detection and topological sort
  export.py       # Deterministic graph.json generator
  check.py        # CLI: structural checks with optional Lean prechecks
  blueprint_view.py # Leanblueprint-style presentation model and DOT export
  publish.py      # Static HTML site generator (Jinja2, MathJax, Graphviz)
  lean_index.py   # Lean 4 declaration extractor
  lean_check.py   # Mechanical Lean reference prechecks
  admit.py        # Staged-to-admitted workflow with review validation

skills/           # Agent prompt templates and report schemas
  mdblueprint-source-extraction/
  mdblueprint-node-review/
  mdblueprint-lean-generation/
  mdblueprint-alignment-review/
  mdblueprint-node-author/
  mdblueprint-publish/

docs/knowledge/
  nodes/          # Admitted knowledge nodes (durable truth)
  staged/         # Candidate nodes awaiting review
  reviews/        # Verifier and referee reports
  requests/       # Proposed new nodes
```

## Status

The core implementation phases are complete, with the publisher now using leanblueprint-style output:

1. **Deterministic core** — parser, validator, DAG, graph.json, static site
2. **Lean integration** — declaration extractor, reference prechecks, sorry detection
3. **Agent contracts** — prompt templates and report schemas for 6 agent roles
4. **Admission workflow** — staged-to-admitted with generality gate and review validation
5. **Leanblueprint-style publisher** — title-first navigation, theorem wrappers, proof folding, keyword pages, and Graphviz dependency views

The full test suite is the source of truth for current coverage and test counts.
