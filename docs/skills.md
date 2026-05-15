# Skills Guide

Skills are reusable workflow guides for Codex, Claude Code, and other agentic coding assistants. They are not the same thing as agents.

An agent is a role-specific LLM call with an input/output contract. A skill teaches an assistant how to run a recurring workflow correctly: which files to inspect, which contract to follow, what it may write, and what must remain deterministic.

The maintained mdblueprint skills live in [`skills/`](../skills/). Each skill has a `SKILL.md` file with YAML frontmatter and optional `references/` files.

## Skill Map

| Task | Use this skill | Main outputs |
| --- | --- | --- |
| Extract theorems, definitions, examples, or proof ideas from a book, PDF, paper, TeX source, or notes | `mdblueprint-source-extraction` | staged nodes, extraction report |
| Create or edit a Markdown knowledge node by hand | `mdblueprint-node-author` | node file |
| Review staged content before admission | `mdblueprint-node-review` | statement/definition review, proof review, admission report |
| Generate Lean code from admitted Markdown nodes | `mdblueprint-lean-generation` | Lean proposal, missing-node requests |
| Check semantic alignment between Markdown and Lean | `mdblueprint-alignment-review` | alignment report |
| Publish or inspect the static site and dependency graph | `mdblueprint-publish` | generated site, `graph.json`, QA notes |

## How To Use A Skill

If the assistant does not auto-discover repo-local skills, open the relevant `skills/<name>/SKILL.md` and follow it manually. Load `references/` files only when the skill points to them and the task needs that schema or template.

Recommended order for building a knowledge base from a book:

1. Use `mdblueprint-source-extraction` to extract candidate definitions, theorems, lemmas, examples, and proof ideas into `docs/knowledge/staged/`.
2. Use `mdblueprint-node-review` to review staged candidates for correctness, proof validity, and generality.
3. Use `tools.knowledge.admit` only after review gates pass.
4. Use `mdblueprint-publish` to validate and publish the generated site.
5. Use `mdblueprint-lean-generation` and `mdblueprint-alignment-review` when connecting admitted nodes to Lean.

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
- extraction reports under `docs/knowledge/reviews/`.

Must not:

- write directly to `docs/knowledge/nodes/`;
- invent dependencies beyond source evidence or existing node ids;
- silently merge distinct statements into one node;
- admit a broader theorem than the source supports.

Use this skill for “从书里面抓出定理”, theorem mining from PDFs, source-to-node extraction, and first-pass knowledge-base formation.

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

### `mdblueprint-alignment-review`

Use when checking whether Lean declarations match Markdown nodes.

Reads:

- Markdown node and dependencies;
- Lean declaration signature or source;
- mechanical precheck output.

Writes:

- alignment reports under `docs/knowledge/reviews/`.

Must not:

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
