# Agent Contracts

LLM agents produce proposals and reports. They do not generate the final site, final graph, or final admitted truth.

An agent is a fixed-role Codex or LLM call with a written contract. It may be implemented as a one-shot Codex invocation, a subagent launched by an orchestrator, or a CLI command that packages context and calls an LLM. The important point is the contract, not whether the process is long-running.

Every agent must define:

- input files and context budget;
- output files;
- allowed write locations;
- forbidden write locations;
- decision vocabulary;
- uncertainty behavior;
- whether it may propose new nodes.

## Execution Model

The v1 implementation can treat every agent as a one-shot call:

```text
Python or human workflow
  -> collect input bundle
  -> invoke fixed-role Codex or LLM prompt
  -> validate output shape
  -> write staged files, reports, or requests
```

Later versions may run agents through a queue or orchestrator, but that should not change the contracts below.

## KB-Only Reasoning Mode

KB-only reasoning is for answering from admitted mdblueprint knowledge, not from
the whole repository.

Allowed default inputs:

- `docs/knowledge/nodes/**/*.md`;
- `docs/knowledge/mdblueprint.yml`;
- exact `topics.md` catalogs when they affect retrieval or display;
- deterministic graph/index data generated from admitted nodes.

Forbidden by default:

- staged candidates, reviews, and requests;
- Lean source files;
- source PDFs, books, and TeX files;
- implementation files;
- internet access;
- uncited model memory.

Use the deterministic context packer to construct the bundle:

```bash
uv run python -m tools.knowledge.context_pack docs/knowledge --target <node-id>
uv run python -m tools.knowledge.context_pack docs/knowledge --topic <topic-id>
```

Use `--include-staged` only when the user explicitly asks for provisional
non-admitted evidence. Answers must cite node ids and state when the bundle does
not contain the requested fact.

## Common Report Header

Every report-like output should start with structured metadata:

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

The Markdown body of a report can explain reasons, but the decision must be machine-readable.

## Agent Summary

| Agent | Main job | Writes | Cannot write |
| --- | --- | --- | --- |
| Source-to-MD | Extract staged nodes from sources | `docs/knowledge/staged/`, `docs/knowledge/reviews/` | `docs/knowledge/nodes/` |
| Definition/Statement Verifier | Review statement correctness and generality | `docs/knowledge/reviews/` | admitted nodes |
| Proof Verifier | Review proof body or proof sketch | `docs/knowledge/reviews/` | admitted nodes |
| Proof-Fill Generator | Generate a local proof for one node | candidate proof text (in-memory until verifier accepts) | any file directly |
| Proof-Fill Verifier | Independently verify the candidate proof | node body + `verification.proof` only on `accepted` | any file if verdict is `gap` or `critical` |
| MD-to-Lean Generator | Generate Lean proposal from admitted nodes | Lean patch proposal, `docs/knowledge/requests/` | admitted nodes without request |
| MD-Lean Alignment Verifier | Judge semantic alignment | `docs/knowledge/reviews/` | final status directly |
| Admission Referee | Decide whether reports justify admission | admission report, optional controlled move | direct mathematical rewriting without record |

External-theorem nodes bypass Source-to-MD extraction and are admitted directly after
alignment verification. See section 4 for details.

## Requests Format

Report files under `docs/knowledge/requests/` follow the schema defined in
[node-format.md](node-format.md#requests-format). Every agent that may propose new
nodes must write a request file rather than creating a staged candidate directly.
The request file is the machine-readable justification that the Admission Referee
evaluates.

## 1. Source-to-MD Agent

Purpose: convert PDFs, books, papers, TeX, or notes into staged Markdown candidate nodes.

Inputs:

- source files;
- source manifests;
- topic directory target;
- optional existing node index.

Outputs:

- candidate Markdown files under `docs/knowledge/staged/`;
- source span metadata;
- generality questions;
- uncertainty notes in a review file if needed.

Decision vocabulary:

```text
extracted
partial
uncertain
blocked
```

May propose new nodes: yes, but only as staged candidates with source locators.

Rules:

- It may extract definitions, theorems, examples, and proof ideas.
- It must not write admitted nodes directly.
- It must not invent dependencies beyond what it can justify from the source or existing node index.
- If the source statement is narrower than the likely reusable mathematical form, it should propose the broader form as a question, not as admitted truth.
- Before creating a staged candidate, it must search the existing node index (admitted and staged) for a node covering the same content. If a near-duplicate exists, it should write a review or request noting the overlap instead of creating a second staged file.

## 2. MD Node Verifiers

There should be two verifier types, because definition checking and proof checking fail in different ways.

Definition and statement verifier:

- checks that assumptions are explicit;
- checks notation is introduced locally or by dependencies;
- checks whether the statement is too special or too broad;
- asks the central generality question: "What is the most general useful form of this statement, and is the current form acceptable?";
- returns `accepted`, `needs_revision`, or `rejected`.

Inputs:

- staged or admitted node;
- dependency node bodies;
- source spans when available;
- project notation conventions when available.

Outputs:

- review report under `docs/knowledge/reviews/`;
- optional revision request under `docs/knowledge/requests/`.

May propose new nodes: only as a request when a dependency is missing or a statement should be split.

Proof verifier:

- checks that the proof body or proof sketch actually proves the stated result;
- identifies gaps, hidden assumptions, circular dependencies, and misuse of prior nodes;
- returns `accepted`, `gap`, or `critical`.

Inputs:

- node statement;
- proof body or proof sketch;
- dependencies named by `uses`;
- relevant source spans or Lean declarations if available.

Outputs:

- proof review report under `docs/knowledge/reviews/`;
- gap list with exact dependency or argument failures.

May propose new nodes: only as a request for a missing lemma that is mathematically reusable.

Both verifiers write reports. They do not directly edit admitted truth unless a later implementation grants a controlled fixer role.

## 3. MD-to-Lean Generator

Purpose: produce Lean declarations, proof skeletons, or implementation plans from admitted Markdown nodes.

Inputs:

- admitted node;
- dependency nodes;
- Lean declaration index;
- existing Lean modules.

Outputs:

- Lean patch proposal or generated Lean file;
- optional `requests/` entry for missing auxiliary nodes;
- optional review note explaining formalization choices.

Decision vocabulary:

```text
generated
blocked_by_missing_node
blocked_by_missing_definition
blocked_by_lean_error
request_human
```

May propose new nodes: yes, but only through `docs/knowledge/requests/`.

Rules:

- It may not silently create admitted knowledge nodes.
- It may propose a new node only with a strong reason.
- A new-node request must explain:
  - why the existing nodes are insufficient;
  - why the result should not remain a local Lean lemma;
  - the proposed most general statement;
  - dependencies;
  - source or mathematical justification;
  - whether the node is a definition, lemma, theorem, example, or task.

## 4. External-Theorem Admission Path

`external-theorem` nodes reference results that are already proved in Lean (Mathlib or
another library). They do not go through the staged extraction flow. Instead:

```text
human or Source-to-MD agent identifies the external theorem
  -> creates an admitted external-theorem node directly, with lean section filled
  -> MD-Lean Alignment Verifier checks that the Markdown statement matches the Lean signature
  -> Admission Referee reviews alignment report and confirms admission
```

Because the proof already exists in Lean, no proof verifier report is required.
The statement verifier is still recommended to check that the Markdown formulation is
mathematically accurate and not more or less general than the Lean declaration.

Required for external-theorem admission (no staged phase):

- `lean.modules` and `lean.declarations` filled and mechanically verified to exist;
- statement verifier report: `accepted`;
- alignment verifier report: `aligned` or `lean_stronger` with a note explaining the
  acceptable discrepancy;
- generality gate: required (same as for theorem kind).

## 5. MD-Lean Alignment Verifier

Purpose: decide whether a Lean declaration semantically matches the Markdown node.

This is an LLM semantic verifier, preceded by deterministic Python prechecks.

Python prechecks:

- referenced Lean modules can be found;
- referenced Lean declarations can be indexed;
- declarations have source locations;
- obvious `sorry` or `admit` markers are reported;
- node YAML has valid `lean.modules` and `lean.declarations` fields.

LLM semantic alignment:

- checks whether the Lean theorem expresses the same mathematical claim as the Markdown statement;
- reports extra hypotheses, missing hypotheses, weakened conclusions, strengthened conclusions, or specialization;
- checks whether a Lean definition has the same mathematical meaning as the Markdown definition;
- returns an alignment report, not an automatic truth update.

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

May propose new nodes: no. It may request a review if the mismatch reveals a missing concept.

## 6. Admission Referee

Purpose: decide whether staged nodes and review reports are sufficient to admit a node.

Inputs:

- staged candidate node;
- statement or definition verifier report;
- proof verifier report if proof content exists;
- generality gate answer;
- deterministic Python check report.

Outputs:

- admission report;
- if approved by workflow, a controlled copy or move into `docs/knowledge/nodes/`.

Decision vocabulary:

```text
admit
needs_revision
needs_human_decision
reject
```

May propose new nodes: no.

Rules:

- It must not hide uncertainty.
- It must not admit a node if dependencies are missing or cyclic.
- It must not admit a node without a completed generality gate.
- It must not admit a definition or concept without
  `verification.definition: accepted`.
- It must not admit a lemma, proposition, theorem, or external-theorem without
  `verification.statement: accepted`.
- It must not admit theorem-like proof content without
  `verification.proof: accepted`.
- It must not mark a node `formalized` or `proved` unless `lean.modules` and
  `lean.declarations` identify the corresponding Lean declarations.
- If reports disagree, it should request human decision instead of resolving silently.

The deterministic path is the Python pipeline:

```bash
uv run python -m tools.knowledge.admission_pipeline docs/knowledge/staged/example.md docs/knowledge
```

The pipeline reports `schema`, `generality`, `verification`, `reviews`, `dag`,
and `write` gates. Agents should cite that report in review or issue comments
instead of manually copying staged files into `docs/knowledge/nodes/`.

## 7. Proof-Fill Agents

The proof-fill agents handle a bounded repair loop that fills a single, local
natural-language proof gap. They are invoked only after the statement verifier
has accepted the node and the proof verifier has returned `gap` for a step that
can be completed from the node's existing `uses` list.

### 7.1 Proof-Fill Generator

Purpose: write a short local proof for the target node using only facts already
listed in the node's `uses` field.

Inputs:

- target node frontmatter and body;
- body text of every dependency listed in `uses`;
- optional `repair_hint` from the verifier (on a repair round).

Outputs:

- JSON object with fields `decision`, `proof`, `reason`, `used_node_ids`;
- proof text is held in memory until the verifier accepts it.

Decision vocabulary:

```text
filled
cannot_fill
```

May propose new nodes: no. It must not add entries to `uses`, change the
statement, or name facts outside the supplied context.

Rules:

- The target node's statement is authoritative and fixed.
- Proof text must be valid Markdown with no placeholders or ellipses.
- If a valid local proof cannot be written from the allowed context, it must
  return `cannot_fill` with a reason.

### 7.2 Proof-Fill Verifier

Purpose: independently verify the candidate proof without access to the
generator's reasoning chain.

Inputs:

- target node frontmatter and body (same bundle as given to the generator);
- allowed dependency bodies;
- candidate proof text only (no generator context or chain-of-thought).

Outputs:

- JSON object with fields `verdict`, `verification_report`, `gaps`,
  `critical_errors`, `repair_hint`;
- on `accepted`: the node body and `verification.proof: accepted` may be
  written by the invoking workflow.

Decision vocabulary:

```text
accepted
gap
critical
```

May propose new nodes: no.

Rules:

- It must verify the proof sequentially, step by step.
- It must reject any use of facts not present in the allowed dependencies.
- It must not be called with the generator's chain-of-thought visible.
- `gap` means a fixable missing step; a `repair_hint` must be included.
- `critical` means a fundamental error requiring human review; no repair loop
  should continue.
- The verifier writes to the node body only when `verdict` is `accepted` and
  is invoked through the skill workflow.

Repair loop:

- The invoking skill passes `repair_hint` back to the generator for at most
  two repair rounds, then re-verifies.
- If `verdict` is still not `accepted` after two rounds, a failure report is
  written under `docs/knowledge/reviews/` and the node is not edited.

## PDF and Source Extraction

A PDF extraction agent can extract key information from documents, but only into staged candidates.

Expected extraction output:

- candidate node files;
- source artifact path;
- page, chapter, theorem number, or other locator;
- confidence or uncertainty note;
- proposed dependencies;
- generality question.

If the source statement is ambiguous, the extractor should preserve the source-local version and ask whether the project wants a more general normalized statement.

## LLM Failure Mode

LLM agents should fail by producing a report with:

- decision;
- reason;
- cited node ids or source spans;
- proposed next action.

They should not silently repair admitted truth.
