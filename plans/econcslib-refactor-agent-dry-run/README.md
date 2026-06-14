# EconCSLib Graph-Refactor Agent Dry Run

This harness runs the graph-refactor workflow against the full EconCSLib
mdblueprint knowledge base without editing EconCSLib node files.

Default knowledge root:

```text
/home/user/EconCSLib/docs/knowledge
```

The runner creates a timestamped directory under:

```text
plans/econcslib-refactor-agent-dry-run/results/
```

Each run directory contains:

- `baseline/`: structural check, lint, and stats output;
- `index/staged-index.json`: deterministic index of staged node ids for
  duplicate-request avoidance;
- `targets/`: selected high-impact target nodes and topics;
- `packs/`: bounded `refactor_pack` bundles for those targets;
- `agent-prompt.md`: the exact prompt passed to Codex;
- `reports/`: expected location for the graph-refactor report;
- `requests/`: expected location for request-backed proposed nodes;
- `dry-runs/`: expected location for dry-run plans and dry-run JSON output;
- `logs/`: Codex JSONL events and the final assistant message.

Run the full dry run from the mdblueprint repo root:

```bash
bash plans/econcslib-refactor-agent-dry-run/run.sh
```

Useful variants:

```bash
# Prepare evidence and prompt only; do not launch Codex.
RUN_AGENT=0 bash plans/econcslib-refactor-agent-dry-run/run.sh

# The default includes staged EconCSLib nodes in packs and dry-run validation.
INCLUDE_STAGED=1 bash plans/econcslib-refactor-agent-dry-run/run.sh

# Restrict packs and dry-run validation to admitted nodes only.
INCLUDE_STAGED=0 bash plans/econcslib-refactor-agent-dry-run/run.sh

# Change how many hot spots and topics are packed.
TOP_N=12 TOPIC_LIMIT=12 bash plans/econcslib-refactor-agent-dry-run/run.sh

# Override the model used by codex exec.
CODEX_MODEL=gpt-5 bash plans/econcslib-refactor-agent-dry-run/run.sh
```

The generated agent prompt instructs Codex to write only inside the run
directory. It should not modify `/home/user/EconCSLib/docs/knowledge` or any
admitted node files.
