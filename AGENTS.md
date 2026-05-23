# AGENTS.md

This file is the working contract for coding agents in the mdblueprint
repository. It is written for Codex, Claude Code, OpenCode, and similar tools.
If your agent does not auto-load this file, open it manually before editing.

## Project Purpose

mdblueprint is a Markdown-first blueprint system for mathematical knowledge
bases that need to connect to Lean. Small Markdown files are the durable source
of truth. Deterministic Python tools validate nodes, build the dependency DAG,
check mechanical Lean references, export graph JSON, and publish a
leanblueprint-style static site.

The boundary is strict:

- Humans and agents may propose staged nodes, reviews, Lean patches, and
  alignment reports.
- Python tools generate final graph data, reverse dependencies, static HTML, and
  browser graph projections.
- Admitted mathematical truth lives under `docs/knowledge/nodes/`.

Do not hand-edit generated graph or site artifacts.

## Repository Structure

```text
tools/knowledge/
  models.py          dataclasses for nodes, sources, Lean refs, diagnostics
  parser.py          Markdown plus YAML frontmatter parser
  validator.py       schema, status, source, and math validation
  graph.py           dependency DAG builder and cycle detection
  export.py          deterministic graph and topic-subgraph exports
  check.py           structural checker CLI
  publish.py         static-site publisher
  lean_index.py      Lean declaration indexer
  lean_check.py      mechanical Lean reference checks
  econcslib_gate.py  real-library integration gate
  templates/         generated-site HTML, CSS, and graph JavaScript

docs/
  architecture.md        system design and non-goals
  agent-contracts.md     role contracts for LLM workflows
  node-format.md         node YAML and Markdown contract
  math-authoring.md      supported math syntax and KaTeX rules
  publisher-and-dag.md   graph, DAG, and published artifact contract
  lean-repositories.md   Lean repository linking and source URL contract
  skills.md             how to use project skills

docs/knowledge/
  mdblueprint.yml    project config
  nodes/             admitted nodes
  staged/            candidates under review
  reviews/           verifier and referee reports
  requests/          proposed missing or revised nodes

skills/
  mdblueprint-*/     reusable workflow skills for agents and humans

tests/
  test_*.py          pytest coverage for parser, checker, publisher, graph,
                    Lean linking, docs contracts, and integration gates
```

## Development Commands

Run all commands from the repository root.

```bash
# Install dependencies
uv sync --extra dev

# Full test suite
uv run --extra dev python -m pytest -q

# Focused checks after graph or publisher changes
uv run --extra dev python -m pytest tests/test_export.py tests/test_publish.py tests/test_graph_navigation_docs.py -q

# Validate the bundled example knowledge base
uv run python -m tools.knowledge.check docs/knowledge

# Publish a local preview outside the knowledge source tree
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site

# Browser render check for a generated site
uv run --extra browser python -m tools.knowledge.render_check /tmp/mdblueprint-site

# Local dev server (dynamic; auto-reloads on .md/.yml changes)
uv run --extra serve python -m tools.knowledge.serve docs/knowledge
# or, after install:
uv run --extra serve mdblueprint-serve docs/knowledge --port 8080
```

The dev server holds the knowledge base in memory and renders pages
on-demand. It mirrors the static-site URL structure exactly, so any URL that
works against a published site also works against `localhost:8080`. The
server is meant for local iteration only — production builds still use
`mdblueprint-publish`.

# Real-library gate against EconCSLib
uv run --extra browser python -m tools.knowledge.econcslib_gate --render-mode smoke
```

Install the browser runtime once before Playwright-backed checks:

```bash
uv run --extra browser playwright install chromium
```

## Editing Rules

- Prefer existing module boundaries and tests over new abstractions.
- Use `rg` for search and inspect nearby code before editing.
- Use deterministic parsers and project helpers for node or graph data. Do not
  parse YAML, Markdown, or graph JSON with fragile string edits when a local API
  exists.
- Do not hand-edit generated graph or site artifacts such as `graph.json`,
  `graph_topics.json`, `subgraphs/topics/*.json`, `node_payloads/*.json`, or
  generated HTML.
- Publish local previews to `/tmp/...` or another build directory outside
  `docs/knowledge`.
- Keep source nodes mathematical. Do not put process notes, implementation
  plans, or reviewer chatter in node bodies.
- If you touch shared behavior, add or update focused tests before claiming the
  task is done.

## Parallel Agent Contract

Treat GitHub issues as the coordination queue. Each agent should work a bounded
issue or explicitly named file set.

- Use one branch or worktree per agent task when multiple agents may overlap.
- Do not rewrite another agent's files.
- Do not force-push shared branches.
- Do not clean untracked files unless you created them and they are clearly
  temporary.
- Before editing a file that may be shared, check `git status --short --branch`
  and inspect the current diff.
- If two agents need the same files, split the work by responsibility first:
  for example tests vs templates, docs vs implementation, or parser vs
  publisher.
- Close an issue only after the relevant tests, checks, or gate commands pass.

## GitHub Issue Workflow

GitHub issues are the coordination queue for this project. Agents read issues
to understand scope and write back to close the loop.

### Authentication

`gh` requires a token. Load it from the environment before any `gh` command:

```bash
# Token is stored in ~/.zshrc as GH_TOKEN
source ~/.zshrc
```

The repo slug is `gametheoryinlean/mdblueprint`.

### Reading Issues

```bash
# List all open issues
gh issue list --repo gametheoryinlean/mdblueprint --state open

# Read a specific issue (full body + comments)
gh issue view <number> --repo gametheoryinlean/mdblueprint --comments

# Search for related issues
gh issue list --repo gametheoryinlean/mdblueprint --search "keyword" --state all
```

### Writing to Issues

```bash
# Add a label
gh issue edit <number> --repo gametheoryinlean/mdblueprint --add-label "bug"

# Post a comment (progress update, question, or resolution note)
gh issue comment <number> --repo gametheoryinlean/mdblueprint \
  --body "Implemented in commit abc1234. Tests pass."

# Close an issue after verification
gh issue close <number> --repo gametheoryinlean/mdblueprint \
  --comment "Resolved: <brief explanation>"
```

Close an issue **only after** the relevant tests, checks, or gate commands pass.

### Pull Requests

```bash
# Create a PR targeting main
gh pr create --repo gametheoryinlean/mdblueprint \
  --title "feat: description" \
  --body "Closes #<number>. <summary of changes and test plan>"

# Check CI status on a PR
gh pr checks <number> --repo gametheoryinlean/mdblueprint
```

## GitHub Sync Contract

`main` is the shared integration branch. Keep it fast-forwardable.

```bash
# Before starting
git status --short --branch
git fetch origin
git pull --ff-only origin main

# During work
git status --short
git diff --check

# After verification on main
git push origin main
```

For feature branches, rebase or fast-forward from `origin/main` before final
verification. Avoid merge commits unless the maintainer explicitly wants one.

## EconCSLib Relationship

mdblueprint is the tooling repository. EconCSLib is the real Lean library and
knowledge-base consumer used to prove that mdblueprint works on a non-toy
project.

Expected relationship:

- mdblueprint owns parser, checker, graph export, static publishing, templates,
  Lean source-link resolution, skills, and documentation.
- EconCSLib owns its Lean code and its `docs/knowledge` content.
- EconCSLib workflows may run mdblueprint from GitHub `main`. A pushed change to
  mdblueprint `main` can change the next EconCSLib blueprint build.
- Local mdblueprint tests are necessary but not sufficient for broad publisher,
  graph, render, schema, or Lean-link changes. Use the real-library gate when
  those surfaces change.

Run the real gate against a local EconCSLib checkout when available:

```bash
uv run --extra browser python -m tools.knowledge.econcslib_gate \
  --repo-path /path/to/EconCSLib \
  --site-dir /tmp/mdblueprint-econcslib-gate \
  --render-mode smoke
```

Use `--render-mode all` before release-level template, graph JavaScript, math
rendering, or navigation changes.

## Common Task Map

| Task | Start here | Minimum verification |
| --- | --- | --- |
| Node schema or validation | `docs/node-format.md`, `tools/knowledge/validator.py` | `uv run --extra dev python -m pytest tests/test_validator.py tests/test_check.py -q` |
| Graph/DAG behavior | `docs/publisher-and-dag.md`, `tools/knowledge/graph.py`, `tools/knowledge/export.py` | `uv run --extra dev python -m pytest tests/test_export.py tests/test_publish.py tests/test_graph_navigation_docs.py -q` |
| Static site templates | `tools/knowledge/templates/`, `tools/knowledge/publish.py` | publisher tests plus `render_check` on a generated site |
| Lean links or checks | `docs/lean-repositories.md`, `tools/knowledge/lean_index.py`, `tools/knowledge/lean_check.py` | `uv run --extra dev python -m pytest tests/test_lean_index.py tests/test_lean_check.py tests/test_lean_links_publish.py -q` |
| Skills or agent workflow docs | `docs/skills.md`, `skills/mdblueprint-*/SKILL.md` | focused docs tests and manual contract review |
| EconCSLib gate | `tools/knowledge/econcslib_gate.py` | `uv run --extra browser python -m tools.knowledge.econcslib_gate --render-mode smoke` |
| Local dev server | `tools/knowledge/serve.py`, `tools/knowledge/context.py` | `uv run --extra dev --extra serve python -m pytest tests/test_serve.py tests/test_serve_integration.py -q` |
| Auto-promote `status: proved` when a plan supplies the proof | `tools/knowledge/promote_via_plan.py`, `docs/node-format.md` (Proved-via-plan Marker, Auto-promotion) | `uv run --extra dev python -m pytest tests/test_promote_via_plan.py tests/test_blueprint_view.py -q`, then `uv run python -m tools.knowledge.promote_via_plan docs/knowledge --dry-run` |

## Knowledge Node Rules

- Admitted nodes live in `docs/knowledge/nodes/`.
- Candidate nodes live in `docs/knowledge/staged/`.
- Reviews live in `docs/knowledge/reviews/`.
- Requests for missing or revised nodes live in `docs/knowledge/requests/`.
- `uses` is a logical dependency list by node id.
- `proof-plan` nodes describe proof routes. Their route dependencies must not be
  copied onto the target theorem's ordinary dependency list unless they are also
  genuine logical prerequisites of the target.
- A theorem reaches `status: proved` either by direct author edit or via the
  `promote_via_plan` CLI, which writes both `status: proved` and a
  `proved_via_plan: <plan_id>` marker recording the attached plan that supplied
  the proof. Direct claims have no marker; the renderer uses the marker's
  presence to distinguish "proved via plan" (mint) from "fully proved" (deep
  green). The tool is idempotent and never demotes.
- Lean declarations in node frontmatter are mechanical links, not proof that the
  Markdown statement and Lean declaration are semantically aligned.

Read `docs/node-format.md` before editing nodes and
`docs/agent-contracts.md` before producing staged nodes or reviews.

