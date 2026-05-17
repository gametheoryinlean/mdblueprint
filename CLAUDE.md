# CLAUDE.md

Claude Code should use [`AGENTS.md`](AGENTS.md) as the authoritative project
instruction file for this repository.

Minimum startup checklist:

1. Read `AGENTS.md`.
2. Read the task-specific docs it references.
3. Check `git status --short --branch`.
4. Run the focused tests or gate listed for the files you changed before
   reporting completion.

This repository is also used by Codex, OpenCode, and other agents. Follow the
parallel-agent and GitHub sync rules in `AGENTS.md` so concurrent work stays
mergeable.
