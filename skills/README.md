# mdblueprint Skills

This directory contains repo-local Agent Skills for recurring mdblueprint workflows.

Each skill is a directory with a `SKILL.md` file and optional `references/` files. The `SKILL.md` files use standard YAML frontmatter (`name` and `description`) so they can be copied or symlinked into tools that support Agent Skills, including Claude Code and Codex-style skill directories.

## Skill Map

| Task | Skill |
| --- | --- |
| Extract definitions, theorems, lemmas, examples, or proof ideas from a book, PDF, paper, TeX source, or notes | `mdblueprint-source-extraction` |
| Recover a proof, proof sketch, or hint for an existing node from cited source spans | `mdblueprint-source-proof-recovery` |
| Create or edit Markdown knowledge nodes by hand | `mdblueprint-node-author` |
| Review staged nodes before admission | `mdblueprint-node-review` |
| Generate Lean declarations, proof skeletons, or Lean patch proposals | `mdblueprint-lean-generation` |
| Choose existing Lean declarations from a bounded candidate bundle | `mdblueprint-lean-linking` |
| Check whether Lean declarations semantically match Markdown nodes | `mdblueprint-alignment-review` |
| Generate or inspect the static site and dependency graph | `mdblueprint-publish` |
| Answer from admitted KB content only | `mdblueprint-kb-reasoning` |

For existing Lean declarations, run `tools.knowledge.lean_link_candidates`, use
`mdblueprint-lean-linking` to produce a mechanical proposal, validate or apply it
with `tools.knowledge.lean_linking`, then use `tools.knowledge.lean_alignment`
and `mdblueprint-alignment-review` for semantic evidence.

## Use Without Installing

Open the relevant `SKILL.md`, follow its workflow, and load only the referenced files you need. This is enough for humans and for agents that do not auto-discover repo-local skills.

## Install For Claude Code

Claude Code skills follow the Agent Skills `SKILL.md` convention. See the official [Claude Code skills documentation](https://code.claude.com/docs/en/skills) for current behavior. Claude Code discovers skills from `.claude/skills/<skill-name>/SKILL.md` for a project or `~/.claude/skills/<skill-name>/SKILL.md` for user-level skills.

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

## Install For Codex

Codex installations can be configured with different skill roots. In this workspace, personal Codex skills commonly live under `~/.agents/skills/`. Copy or symlink the skill directories there, or into the skill root configured for your Codex environment.

```bash
mkdir -p ~/.agents/skills
cp -R skills/mdblueprint-* ~/.agents/skills/
```

After installation, restart or refresh the agent session if the tool only scans skills at startup.

## Source Of Truth

Keep the repo-local `skills/` directory as the maintained source. Treat copies under `.claude/skills/`, `~/.claude/skills/`, or `~/.agents/skills/` as installed deployments.
