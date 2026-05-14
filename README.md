# mdblueprint

`mdblueprint` is a Markdown-first blueprint system for mathematical knowledge bases that are meant to work with Lean, without making `leanblueprint` or TeX blueprint files the source of truth.

The durable source is a directory of small Markdown nodes:

```text
docs/knowledge/nodes/**/*.md
```

Python tools parse those nodes, validate the dependency DAG, check mechanical Lean references, and generate a blueprint-like static website. LLM agents may extract candidate nodes, review statements and proofs, generate Lean proposals, and judge semantic MD-Lean alignment, but they do not generate the final DAG or website.

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

## First Implementation Target

The first useful version should be deterministic and local:

1. Parse Markdown nodes with YAML frontmatter.
2. Validate required metadata and body hygiene.
3. Build a dependency DAG from `uses`.
4. Emit `graph.json`.
5. Generate a small static website from the parsed nodes.

Semantic review and Lean generation can be layered on top after the deterministic core exists.
