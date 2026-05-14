# Rethlas-Style Markdown Knowledge Pipeline

## Goal

Build a lightweight natural-language knowledge system for mathematical libraries that is compatible with Lean, but does not use `leanblueprint` or TeX blueprint files as the source of truth.

The source of truth is a Markdown knowledge base:

```text
docs/knowledge/nodes/**/*.md
```

The system supports:

- extracting mathematical content from PDFs, books, papers, TeX, notes, and Lean work;
- storing admitted mathematical knowledge as small Markdown nodes;
- maintaining a dependency DAG between nodes;
- generating a blueprint-like website and graph from Markdown by deterministic Python code;
- coordinating LLM agents for extraction, statement review, proof review, Lean generation, and semantic MD-Lean alignment;
- keeping all durable truth under explicit review and admission.

## Non-Goals

- Do not use Kuzu in the first version.
- Do not use `leanblueprint` as the source format.
- Do not make LLMs generate the final website, final DAG, or final graph projection.
- Do not let generators silently create admitted nodes.
- Do not require a daemon, event bus, or long-running service in the first version.

## Core Principle

The Rethlas pattern to migrate is not the database stack. It is the separation of roles:

```text
agents propose and review
Python validates and projects
humans or explicit admission rules decide durable truth
```

For this project:

- LLM agents may create staged candidates, reviews, Lean proposals, and new-node requests.
- Python tools parse Markdown, validate structure, build the DAG, check mechanical Lean references, and generate the static website.
- Only admitted files under `docs/knowledge/nodes/` are durable mathematical knowledge.
- Anything uncertain remains in `staged/`, `reviews/`, or `requests/`.

## Meaning of Agent

An agent is a fixed-role Codex or LLM call with a written contract.

In the first version, an agent can be a single Codex call, a prompt template invoked by a CLI command, or a subagent launched by an orchestrator. It does not need to be a long-running service.

Each agent must have:

- a role name;
- permitted inputs;
- required outputs;
- write permissions;
- forbidden actions;
- a report schema or file format;
- a rule for uncertainty.

This follows the Rethlas style: different roles can reason creatively, but only controlled admission moves information into durable truth.

## Directory Layout

The default project layout is:

```text
docs/knowledge/
  nodes/       # admitted knowledge nodes, organized by topic directories
  staged/      # source-to-MD and generator proposals, not durable truth
  reviews/     # verifier and referee reports
  requests/    # proposed new nodes, generalization questions, Lean bridge requests
  sources/     # source manifests: PDFs, books, chapters, page spans, citations
  site/        # generated static site if committed, otherwise generated output target

tools/knowledge/
  graph.py       # parse nodes and build an in-memory graph model
  check.py       # schema, DAG, dependency, status, and mechanical consistency checks
  lean_index.py  # extract Lean declarations and locations
  publish.py     # generate graph.json and blueprint-like HTML pages
```

The exact Python module names can change during implementation, but these responsibilities should stay separate.

## Admission Rules

The durable admission path is:

```text
staged candidate
  -> statement or definition verification
  -> proof verification if proof content exists
  -> generality review
  -> admitted node under docs/knowledge/nodes/
```

Admission invariants:

- The node id is stable and topic-scoped.
- All dependencies in `uses` exist or are explicitly external.
- The dependency graph is acyclic.
- The Markdown body contains only mathematical content.
- Source information is sufficient for audit when the node comes from a book or paper.
- The verifier has considered the most general useful statement.
- Uncertainty is preserved as a review or request, not hidden in the admitted node.

## Generality Gate

The following kinds must pass a generality gate before admission:

```text
definition
lemma
proposition
theorem
external-theorem
```

The reviewer must explicitly answer:

```text
What is the most general useful form of this statement?
Is the current statement that form?
If not, is the narrower form deliberately chosen?
What assumptions might be removable?
What hypotheses are only artifacts of the source presentation?
```

If the answer is unclear after serious review, the node remains staged or receives
`needs_statement_review` (for theorem/lemma kinds) or `needs_definition_review`
(for definition kinds).

The following kinds are exempt from the generality gate:

```text
concept       — organising ideas rather than mathematical claims; no gate required
example       — intentionally specific by design; no gate required
proof-plan    — a sketch or plan, not a complete mathematical claim; no gate required
task          — a work item, not a mathematical claim; no gate required
```

Exempt kinds may still receive an informal generality note if the reviewer judges it
useful, but this note does not block admission.

## Implementation Phases

Phase 1: deterministic core.

- Markdown node parser;
- schema validator;
- DAG builder;
- graph JSON writer;
- minimal static HTML publisher.

Phase 2: Lean index and mechanical prechecks.

- declaration extraction;
- Lean reference existence checks;
- `sorry` or `admit` reporting.

Phase 3: agent prompt files and report formats.

- source-to-MD agent contract;
- statement and definition verifier contract;
- proof verifier contract;
- MD-to-Lean generator contract;
- MD-Lean semantic alignment verifier contract.

Phase 4: admission workflow.

- staged-to-admitted helper;
- review report validation;
- request format for generator-proposed nodes.

This sequence keeps the project usable before the LLM workflows are fully automated.

## Design Decisions

- Markdown nodes are the source of truth.
- YAML carries system metadata; Markdown body carries only mathematics.
- Topic directories organize the knowledge base.
- Python generates the website and DAG.
- LLMs do semantic work, not deterministic projection.
- Semantic MD-Lean alignment is done by an LLM verifier, with Python prechecks.
- Generator-created nodes are proposals, never direct admissions.
- Definition and proof verification are separate roles.
- Kuzu is intentionally excluded from the first version.
