# Skills Guide

Skills are reusable workflow guides for Codex, Claude Code, and other agentic coding assistants. They are not the same thing as agents.

An agent is a role-specific LLM call with an input/output contract. A skill teaches an assistant how to run a recurring workflow correctly: which files to inspect, which contract to follow, what it may write, and what must remain deterministic.

The maintained mdblueprint skills live in [`skills/`](../skills/). Each skill has a `SKILL.md` file with YAML frontmatter and optional `references/` files.

## Skill Map

| Task | Use this skill | Main outputs |
| --- | --- | --- |
| Extract theorems, definitions, examples, or proof ideas from a book, PDF, paper, TeX source, or notes | `mdblueprint-source-extraction` | staged nodes, extraction report |
| Recover a proof, proof sketch, or hint for an existing node from cited source spans | `mdblueprint-source-proof-recovery` | proposed proof block, recovery report, missing-dependency requests |
| Create or edit a Markdown knowledge node by hand | `mdblueprint-node-author` | node file |
| Review staged content before admission | `mdblueprint-node-review` | statement/definition review, proof review, admission report |
| Generate Lean code from admitted Markdown nodes | `mdblueprint-lean-generation` | Lean proposal, missing-node requests |
| Choose existing Lean declarations for a Markdown node from a bounded candidate bundle | `mdblueprint-lean-linking` | mechanical Lean link proposal |
| Check semantic alignment between Markdown and Lean | `mdblueprint-alignment-review` | alignment report |
| Publish or inspect the static site and dependency graph | `mdblueprint-publish` | generated site, `graph.json`, QA notes |
| Answer from admitted KB content only | `mdblueprint-kb-reasoning` | cited answer, missing-fact report |

## How To Use A Skill

If the assistant does not auto-discover repo-local skills, open the relevant `skills/<name>/SKILL.md` and follow it manually. Load `references/` files only when the skill points to them and the task needs that schema or template.

Recommended order for building a knowledge base from a book:

1. Use `mdblueprint-source-extraction` to extract candidate definitions, theorems, lemmas, examples, and proof ideas into `docs/knowledge/staged/`.
2. Use `mdblueprint-node-review` to review staged candidates for correctness, proof validity, and generality.
3. For existing theorem-like nodes with missing or incomplete proofs, use `mdblueprint-source-proof-recovery` before bounded `mdblueprint-proof-fill` when `source.spans` or source hints exist.
4. Use `tools.knowledge.admission_pipeline` only after review gates pass.
5. Use `mdblueprint-publish` to validate and publish the generated site.
6. Use `tools.knowledge.lean_link_candidates`, `mdblueprint-lean-linking`,
   `tools.knowledge.lean_linking`, and `tools.knowledge.lean_alignment` when
   connecting admitted nodes to existing Lean declarations.
7. Use `mdblueprint-lean-generation` when no suitable existing Lean declaration
   exists and new Lean code is needed.

Admission is deterministic and Python-orchestrated:

```bash
uv run python -m tools.knowledge.admission_pipeline docs/knowledge/staged/example.md docs/knowledge
```

The pipeline requires `verification.definition: accepted` for concepts and
definitions, `verification.statement: accepted` for theorem-like nodes, and
`verification.proof: accepted` when theorem-like proof content is present.
Ordinary admitted nodes may omit Lean metadata; `formalized` and `proved` nodes
must include `lean.modules` and `lean.declarations`.

For KB-only reasoning, use `mdblueprint-kb-reasoning` and a deterministic
context bundle:

```bash
uv run python -m tools.knowledge.context_pack docs/knowledge --target <node-id>
uv run python -m tools.knowledge.context_pack docs/knowledge --topic <topic-id>
```

Default KB-only mode reads admitted nodes only. Staged/review/source/Lean modes
are opt-in and must be labeled as non-admitted evidence.

## Claude Code Compatibility

Claude Code skills follow the Agent Skills `SKILL.md` convention. See the official [Claude Code skills documentation](https://code.claude.com/docs/en/skills) for current behavior. Claude Code discovers skills from:

```text
.claude/skills/<skill-name>/SKILL.md
~/.claude/skills/<skill-name>/SKILL.md
```

The repo-local skill directories are compatible in shape: each has a `SKILL.md` with `name` and `description` frontmatter. To install them for Claude Code, copy or symlink the directories.

Project-local install:

```bash
mkdir -p .claude/skills
cp -R skills/mdblueprint-* .claude/skills/
```

User-level install:

```bash
mkdir -p ~/.claude/skills
cp -R skills/mdblueprint-* ~/.claude/skills/
```

Keep the repo-local `skills/` directory as the source of truth. Treat `.claude/skills/` copies as installed deployments.

## Codex Compatibility

Codex skill roots vary by environment. In this workspace, personal Codex skills commonly live under:

```text
~/.agents/skills/
```

Install by copying or symlinking the repo-local skill directories into the configured Codex skill root:

```bash
mkdir -p ~/.agents/skills
cp -R skills/mdblueprint-* ~/.agents/skills/
```

Then restart or refresh the Codex session if skill discovery happens only at startup.

## Skill Contracts

### `mdblueprint-source-extraction`

Use when converting source material into staged Markdown nodes.

Reads:

- source material;
- existing admitted and staged node index;
- [`docs/node-format.md`](node-format.md);
- `skills/mdblueprint-source-extraction/references/extraction-report-schema.md` when writing the report.

Writes:

- `docs/knowledge/staged/**/*.md`;
- extraction reports under `docs/knowledge/reviews/`;
- request files under `docs/knowledge/requests/` when a proof needs a missing
  reusable dependency.

Proof extraction contract:

- If a theorem-like source item includes proof text, preserve it in the staged
  node as a natural-language `*Proof.*` block.
- Lightly normalize the proof to mdblueprint style and supported math syntax,
  but do not replace the source argument with a new proof.
- Do not set `verification.proof: accepted`; proof review and admission decide
  that later.
- Search admitted + staged nodes for proof dependencies. Add existing node ids to
  `uses` only when they are actual logical dependencies of the proof.
- Record `proof_status` in the extraction report as `full`, `partial`, `absent`,
  or `not_extracted`.
- Missing proof dependencies become report notes or request files, not invented
  admitted/staged facts.
- `proof-fill` is reserved for small local gaps after proof review, not for
  replacing proofs already present in source material.

Must not:

- write directly to `docs/knowledge/nodes/`;
- invent dependencies beyond source evidence or existing node ids;
- drop source proof text and leave admission to proof-fill by default;
- silently merge distinct statements into one node;
- admit a broader theorem than the source supports.

Use this skill for “从书里面抓出定理”, theorem mining from PDFs, source-to-node extraction, and first-pass knowledge-base formation.

### `mdblueprint-source-proof-recovery`

Use when repairing an existing theorem-like node that has missing/incomplete
proof content and cited source spans or source hints.

Reads:

- target node and its `uses` dependencies;
- admitted and staged node index;
- cited source spans only.

Writes:

- source-proof-recovery reports under `docs/knowledge/reviews/`;
- missing-dependency requests under `docs/knowledge/requests/`;
- proposed `*Proof.*` block for staged nodes when the Python orchestrator grants
  a write path.

Must not:

- set `verification.proof: accepted`;
- invoke proof-fill, proof review, or admission by itself;
- read unrelated source material;
- invent dependencies or change the statement.

This skill is the source proof recovery branch of proof repair. If it finds only
a hint, the Python orchestrator may pass that explicit source hint to
`mdblueprint-proof-fill`; proof-fill must not read source files directly.

### `mdblueprint-node-author`

Use when creating or editing a node by hand.

Reads:

- [`docs/node-format.md`](node-format.md);
- `skills/mdblueprint-node-author/references/node-template.md`.

Writes:

- a staged node by default;
- an admitted node only when the human explicitly asks and review evidence exists.

Must not:

- put operational notes in the Markdown body;
- set admitted/proved status without evidence;
- invent dependencies.

### `mdblueprint-node-review`

Use when deciding whether staged content is fit for admission.

Reads:

- staged node;
- dependency nodes;
- review schemas;
- deterministic check output.

Writes:

- statement/definition review reports;
- proof review reports;
- admission referee reports.

Must not:

- resolve verifier disagreement silently;
- skip the generality gate;
- treat plausible prose as admitted truth.

### `mdblueprint-lean-generation`

Use when turning admitted Markdown nodes into Lean proposals.

Reads:

- admitted node;
- dependency nodes;
- Lean declaration index or Lean project context.

Writes:

- Lean patch proposals or generated Lean code when requested;
- missing-node requests under `docs/knowledge/requests/`.

Must not:

- create admitted Markdown nodes directly;
- weaken the Markdown statement without a review note;
- generate final graph data.

### `mdblueprint-lean-linking`

Use when a Markdown node needs a mechanical link to existing Lean declarations.

Reads:

- bounded candidate bundle from `tools.knowledge.lean_link_candidates`;
- candidate signatures, snippets, source URLs, and declaration metadata supplied
  by Python.

Writes:

- one proposal consumed by `tools.knowledge.lean_linking`;
- no direct node edits unless the Python CLI validates and applies the proposal.

Must not:

- scan the whole Lean repository;
- set `verification.alignment`;
- set `status: formalized` or `status: proved`;
- generate new Lean code;
- claim semantic equivalence.

The proposal is a mechanical link only. After it is validated, use
`tools.knowledge.lean_alignment` and `mdblueprint-alignment-review` for semantic
alignment evidence.

### `mdblueprint-alignment-review`

Use when checking whether Lean declarations match Markdown nodes.

Reads:

- bounded bundle from `tools.knowledge.lean_alignment`;
- one Markdown node and one mechanically resolved Lean declaration;
- Lean signature/snippet, docstring, source URL, and declaration metadata supplied
  by Python.

Writes:

- alignment reports under `docs/knowledge/reviews/`.

Must not:

- scan the whole Lean repository;
- update `verification.alignment`;
- update final status directly;
- rely on mechanical existence checks as semantic equivalence;
- ignore extra hypotheses or special cases.

### `mdblueprint-publish`

Use when generating or checking the blueprint-style site and dependency graph.

Runs:

```bash
uv run python -m tools.knowledge.check docs/knowledge
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

Must not:

- call an LLM to generate final HTML or graph data;
- edit node content just to make publishing pass;
- infer missing dependencies.

## Skill Versus Agent Boundary

Example:

```text
User: Extract key definitions from this PDF.

Skill:
  mdblueprint-source-extraction decides the workflow:
    preserve source spans, avoid admission, create staged candidates, write report.

Agent contract:
  Source-to-MD defines the role-specific input/output contract:
    decision vocabulary, allowed writes, forbidden writes, uncertainty behavior.
```

The skill controls process discipline. The agent contract controls role-specific outputs and authority.

## Maintenance Rules

- Keep `SKILL.md` files concise.
- Put schemas and templates in `references/`.
- Keep frontmatter `description` focused on when to use the skill, not a workflow summary.
- Update this guide whenever a skill is added, renamed, or moved.
- After skill edits, run:

```bash
uv run --extra dev python -m pytest -q
git diff --check
```
