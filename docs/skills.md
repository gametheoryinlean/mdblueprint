# Skill Design

Skills are reusable workflow guides for Codex. They are not the same thing as agents.

An agent is a role-specific Codex or LLM call with an input/output contract. A skill teaches Codex how to perform a recurring workflow correctly, including which tools to run, which files to inspect, and which agent contract to invoke.

The first mdblueprint implementation should create skills only when the workflow is repeated enough to justify reuse.

## Skill Layout

Recommended shape:

```text
skills/
  mdblueprint-node-author/
    SKILL.md
    references/node-template.md
  mdblueprint-source-extraction/
    SKILL.md
    references/extraction-report-schema.md
  mdblueprint-node-review/
    SKILL.md
    references/review-report-schema.md
  mdblueprint-lean-generation/
    SKILL.md
    references/new-node-request-schema.md
  mdblueprint-alignment-review/
    SKILL.md
    references/alignment-report-schema.md
  mdblueprint-publish/
    SKILL.md
```

Keep each `SKILL.md` short. Put schemas and templates in `references/`.

## 1. mdblueprint-node-author

Use when creating or editing a Markdown knowledge node by hand.

Responsibilities:

- preserve math-only body rule;
- keep YAML metadata structured;
- choose stable ids;
- place nodes under topic directories;
- keep one concept, definition, theorem, example, or proof-plan per file;
- mark incomplete statements with review status rather than hiding uncertainty.

Must read:

- `docs/node-format.md`;
- node template reference.

Must not:

- add operational sections to the Markdown body;
- invent dependencies without checking existing node ids;
- mark a node admitted without the required review evidence.

## 2. mdblueprint-source-extraction

Use when extracting candidate nodes from a PDF, book, paper, TeX source, or lecture note.

Responsibilities:

- create staged candidates only;
- record source artifacts and locators;
- preserve source-local statements;
- propose normalized or more general statements as questions;
- write uncertainty into reports.

Invokes or follows:

- Source-to-MD Agent.

Must not:

- write directly to `docs/knowledge/nodes/`;
- silently merge several distinct statements into one node;
- invent a broader theorem as admitted truth.

## 3. mdblueprint-node-review

Use when deciding whether a staged node is mathematically fit for admission.

Responsibilities:

- run deterministic Python checks first when available;
- invoke statement/definition verifier for definitions and statements;
- invoke proof verifier when proof content exists;
- enforce the generality gate;
- produce review reports with explicit decisions.

Invokes or follows:

- Definition/Statement Verifier;
- Proof Verifier;
- Admission Referee when moving toward admission.

Must not:

- treat plausible prose as admitted truth;
- skip the generality question;
- resolve verifier disagreement silently.

## 4. mdblueprint-lean-generation

Use when turning admitted Markdown nodes into Lean proposals.

Responsibilities:

- read the admitted node and dependencies;
- inspect existing Lean modules and declaration index;
- generate Lean skeletons or patches;
- propose auxiliary nodes only through `requests/`;
- justify every proposed new node.

Invokes or follows:

- MD-to-Lean Generator.

Must not:

- add admitted Markdown nodes directly;
- generate final DAG edges;
- weaken the mathematical statement without a review note.

## 5. mdblueprint-alignment-review

Use when checking whether a Lean declaration semantically matches a Markdown node.

Responsibilities:

- run Python mechanical prechecks when available;
- package Markdown statement, Lean signature, dependencies, and relevant source snippets;
- invoke semantic alignment verifier;
- write an alignment report.

Invokes or follows:

- MD-Lean Alignment Verifier.

Must not:

- rely on Python to decide semantic equivalence;
- update final status directly from an LLM answer without an admission rule;
- ignore extra hypotheses or specialized Lean versions.

## 6. mdblueprint-publish

Use when generating or checking the blueprint-like website and DAG.

Responsibilities:

- run the Python parser and checker;
- generate `graph.json`;
- generate static HTML pages;
- inspect output for missing nodes, broken links, or graph errors.

Must not:

- call an LLM to generate final HTML or graph data;
- edit node content to make publishing pass;
- infer missing dependencies.

## Skill Versus Agent Boundary

Example:

```text
User: Extract key definitions from this PDF.

Skill:
  mdblueprint-source-extraction decides the workflow:
    read source manifest, choose output directory, preserve spans, avoid admission.

Agent:
  Source-to-MD Agent performs the role-specific extraction and emits staged files plus a report.
```

The skill controls process discipline. The agent performs one bounded reasoning task.
