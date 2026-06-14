#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

KB_ROOT="${KB_ROOT:-/home/user/EconCSLib/docs/knowledge}"
KB_REPO_ROOT="${KB_REPO_ROOT:-/home/user/EconCSLib}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="${RUN_ROOT:-$SCRIPT_DIR/results/$RUN_ID}"
TOP_N="${TOP_N:-10}"
TOPIC_LIMIT="${TOPIC_LIMIT:-12}"
INCLUDE_STAGED="${INCLUDE_STAGED:-1}"
PACK_LINT="${PACK_LINT:-0}"
RUN_AGENT="${RUN_AGENT:-1}"
CODEX_MODEL="${CODEX_MODEL:-}"

UV=(uv --cache-dir /tmp/uv-cache run)

mkdir -p \
  "$RUN_ROOT/baseline" \
  "$RUN_ROOT/index" \
  "$RUN_ROOT/targets" \
  "$RUN_ROOT/packs/targets" \
  "$RUN_ROOT/packs/topics" \
  "$RUN_ROOT/reports" \
  "$RUN_ROOT/requests" \
  "$RUN_ROOT/dry-runs" \
  "$RUN_ROOT/logs"

run_capture() {
  local name="$1"
  shift
  local out="$RUN_ROOT/baseline/$name"
  set +e
  "$@" > "$out" 2> "$out.stderr"
  local code=$?
  set -e
  printf '%s\n' "$code" > "$out.exit"
}

write_metadata() {
  {
    printf 'run_id: %s\n' "$RUN_ID"
    printf 'created_at_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'repo_root: %s\n' "$REPO_ROOT"
    printf 'kb_root: %s\n' "$KB_ROOT"
    printf 'kb_repo_root: %s\n' "$KB_REPO_ROOT"
    printf 'include_staged: %s\n' "$INCLUDE_STAGED"
    printf 'pack_lint: %s\n' "$PACK_LINT"
    printf 'top_n: %s\n' "$TOP_N"
    printf 'topic_limit: %s\n' "$TOPIC_LIMIT"
    printf 'mdblueprint_commit: '
    git -C "$REPO_ROOT" rev-parse HEAD
    printf 'mdblueprint_status:\n'
    git -C "$REPO_ROOT" status --short --branch | sed 's/^/  /'
    if git -C "$KB_REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      printf 'econcslib_commit: '
      git -C "$KB_REPO_ROOT" rev-parse HEAD
      printf 'econcslib_status:\n'
      git -C "$KB_REPO_ROOT" status --short --branch | sed 's/^/  /'
    fi
  } > "$RUN_ROOT/metadata.yml"
}

write_metadata

cd "$REPO_ROOT"

STATS_STAGED_ARGS=()
PACK_STAGED_ARGS=()
PACK_LINT_ARGS=()
if [[ "$INCLUDE_STAGED" == "1" ]]; then
  PACK_STAGED_ARGS=(--include-staged)
else
  STATS_STAGED_ARGS=(--no-include-staged)
fi
if [[ "$PACK_LINT" != "1" ]]; then
  PACK_LINT_ARGS=(--no-lint)
fi

DRY_RUN_STAGED_FLAG=""
if [[ "$INCLUDE_STAGED" == "1" ]]; then
  DRY_RUN_STAGED_FLAG=" --include-staged"
fi

run_capture check.txt "${UV[@]}" python -m tools.knowledge.check "$KB_ROOT"
run_capture lint.json "${UV[@]}" mdblueprint-lint "$KB_ROOT" --json --no-llm
run_capture lint.txt "${UV[@]}" mdblueprint-lint "$KB_ROOT" --no-llm
run_capture stats.json "${UV[@]}" python -m tools.knowledge.stats "$KB_ROOT" --json --top "$TOP_N" "${STATS_STAGED_ARGS[@]}"
run_capture stats.txt "${UV[@]}" python -m tools.knowledge.stats "$KB_ROOT" --top "$TOP_N" "${STATS_STAGED_ARGS[@]}"

"${UV[@]}" python - "$KB_ROOT" "$RUN_ROOT/index/staged-index.json" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.knowledge.export import leaf_topic_ids_for_node
from tools.knowledge.parser import scan_directory

root = Path(sys.argv[1])
out = Path(sys.argv[2])
staged_dir = root / "staged"
nodes = scan_directory(staged_dir) if staged_dir.exists() else []

payload = {
    "kind": "mdblueprint-staged-index",
    "knowledge_root": str(root),
    "staged_count": len(nodes),
    "nodes": [
        {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
            "primary_topic": node.primary_topic,
            "topics": leaf_topic_ids_for_node(node),
            "uses": list(node.uses or []),
            "file_path": str(node.file_path) if node.file_path else None,
        }
        for node in sorted(nodes, key=lambda item: item.id)
    ],
}

out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY

"${UV[@]}" python - "$RUN_ROOT/baseline/stats.json" "$RUN_ROOT/targets/hotspots.txt" "$RUN_ROOT/targets/topics.txt" "$TOP_N" "$TOPIC_LIMIT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

stats_path = Path(sys.argv[1])
hotspots_path = Path(sys.argv[2])
topics_path = Path(sys.argv[3])
top_n = int(sys.argv[4])
topic_limit = int(sys.argv[5])

stats = json.loads(stats_path.read_text(encoding="utf-8"))

hotspots: list[str] = []
for section in ("hot_spots_in_degree", "hot_spots_out_degree"):
    for item in stats.get(section, [])[:top_n]:
        node_id = item.get("node_id")
        if isinstance(node_id, str) and node_id not in hotspots:
            hotspots.append(node_id)

topics = [
    topic
    for topic, _count in sorted(
        stats.get("topics", {}).items(),
        key=lambda item: (-item[1], item[0]),
    )[:topic_limit]
]

hotspots_path.write_text("\n".join(hotspots) + ("\n" if hotspots else ""), encoding="utf-8")
topics_path.write_text("\n".join(topics) + ("\n" if topics else ""), encoding="utf-8")
PY

safe_name() {
  printf '%s' "$1" | tr -c 'A-Za-z0-9_.-' '_'
}

while IFS= read -r node_id; do
  [[ -n "$node_id" ]] || continue
  out="$RUN_ROOT/packs/targets/$(safe_name "$node_id").json"
  set +e
  "${UV[@]}" python -m tools.knowledge.refactor_pack "$KB_ROOT" --target "$node_id" "${PACK_STAGED_ARGS[@]}" "${PACK_LINT_ARGS[@]}" > "$out" 2> "$out.stderr"
  code=$?
  set -e
  printf '%s\n' "$code" > "$out.exit"
done < "$RUN_ROOT/targets/hotspots.txt"

while IFS= read -r topic_id; do
  [[ -n "$topic_id" ]] || continue
  out="$RUN_ROOT/packs/topics/$(safe_name "$topic_id").json"
  set +e
  "${UV[@]}" python -m tools.knowledge.refactor_pack "$KB_ROOT" --topic "$topic_id" "${PACK_STAGED_ARGS[@]}" "${PACK_LINT_ARGS[@]}" > "$out" 2> "$out.stderr"
  code=$?
  set -e
  printf '%s\n' "$code" > "$out.exit"
done < "$RUN_ROOT/targets/topics.txt"

cat > "$RUN_ROOT/agent-prompt.md" <<PROMPT
You are testing the mdblueprint graph-refactor agent on the EconCSLib knowledge base.

Use the repo-local skill:

- skills/mdblueprint-graph-refactor-review/SKILL.md

Knowledge root:

- $KB_ROOT

Run directory:

- $RUN_ROOT

Scope:

- Staged content mode is ${INCLUDE_STAGED}.
- If staged content mode is 1, review the admitted+staged EconCSLib graph. Treat staged nodes in packs as existing graph nodes for dependency existence, reachability, duplicate/overlap, topic, and formulation-impact analysis. This does not admit them and is not a prompt to propose staged-node promotion.
- If staged content mode is 0, review the admitted graph. Use the staged id index only to avoid duplicate missing-node requests; if a missing dependency id already exists under staged/, note that it is outside admitted scope instead of proposing a new node or a staged-promotion proposal.
- This is a dry run. Do not edit EconCSLib node files, staged files, generated artifacts, or source files.
- Write outputs only under the run directory.

Precomputed deterministic evidence:

- $RUN_ROOT/metadata.yml
- $RUN_ROOT/baseline/check.txt
- $RUN_ROOT/baseline/lint.json
- $RUN_ROOT/baseline/lint.txt
- $RUN_ROOT/baseline/stats.json
- $RUN_ROOT/baseline/stats.txt
- $RUN_ROOT/index/staged-index.json
- $RUN_ROOT/targets/hotspots.txt
- $RUN_ROOT/targets/topics.txt
- $RUN_ROOT/packs/targets/*.json
- $RUN_ROOT/packs/topics/*.json

Note: baseline lint is collected separately. Per-target and per-topic packs are
collected with PACK_LINT=$PACK_LINT for scalability.

Task:

1. Read the graph-refactor skill and its references:
   - refactor-report-schema.md
   - formulation-impact.md
   - dry-run-plan-schema.md
2. Use the precomputed baselines and packs as the primary evidence.
3. Propose high-impact graph refactors. Prioritize:
   - redundant or missing logical dependencies;
   - formulation-sensitive impact risks around high in-degree nodes;
   - topic moves or memberships that improve navigation without fabricating dependencies;
   - duplicate/overlap, split, generalization, or request-needed opportunities;
   - Lean/topic divergence only when justified by the evidence.
4. Keep the proposal list bounded. Prefer the best 8-15 proposals over exhaustive coverage.
5. For any proposal that modifies, weakens, strengthens, replaces, or deletes a node or dependency, include formulation-sensitive impact analysis.
6. Before writing any new-node or missing-dependency request, check $RUN_ROOT/index/staged-index.json. Do not create a request for an id that already exists in the loaded graph or staged index. Do not add a staged-node promotion/review proposal kind; that belongs to the Admission Referee workflow.
7. For any new-node, split-node, missing-dependency, or generalization proposal that remains after the staged-index check, write request files under:
   - $RUN_ROOT/requests/
8. For concrete mechanical actions, write an explicit dry-run plan under:
   - $RUN_ROOT/dry-runs/refactor-plan.yml
   Use only operations supported by dry-run-plan-schema.md.
9. Run these validators before finishing:
   - uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_report_check "$KB_ROOT" "$RUN_ROOT/reports/econcslib-graph-refactor-report.md"
   - uv --cache-dir /tmp/uv-cache run python -m tools.knowledge.refactor_dry_run "$KB_ROOT" "$RUN_ROOT/dry-runs/refactor-plan.yml"$DRY_RUN_STAGED_FLAG --json
10. Save the report here:
   - $RUN_ROOT/reports/econcslib-graph-refactor-report.md
11. Save dry-run JSON here:
   - $RUN_ROOT/dry-runs/refactor-dry-run.json
12. Save a short human summary here:
   - $RUN_ROOT/SUMMARY.md

Report requirements:

- Use agent: graph-refactor-proposer.
- Use decision: proposals, no_action, needs_human_decision, or blocked.
- Cite concrete node ids and evidence pack paths.
- Do not rely on graph reachability alone for descendant impact.
- Do not claim a dry-run validates mathematical truth. It validates structural effects only.
- Preserve uncertainty as semantic-review, request-needed, blocked, or needs_human_decision.

Final response:

- List the output files written.
- State whether report validation passed.
- State whether dry-run simulation introduced structural errors.
- Mention any blockers.
PROMPT

cat > "$RUN_ROOT/run-codex.sh" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO_ROOT"
CODEX_CMD=(codex --ask-for-approval never exec -C "$REPO_ROOT" --add-dir "$KB_REPO_ROOT" --sandbox workspace-write --output-last-message "$RUN_ROOT/logs/agent-last-message.md" --json)
if [[ -n "\${CODEX_MODEL:-$CODEX_MODEL}" ]]; then
  CODEX_CMD+=(-m "\${CODEX_MODEL:-$CODEX_MODEL}")
fi
"\${CODEX_CMD[@]}" - < "$RUN_ROOT/agent-prompt.md" | tee "$RUN_ROOT/logs/codex-events.jsonl"
SCRIPT
chmod +x "$RUN_ROOT/run-codex.sh"

echo "Prepared EconCSLib graph-refactor run directory:"
echo "$RUN_ROOT"
echo
echo "Targets:"
echo "- $(wc -l < "$RUN_ROOT/targets/hotspots.txt" | tr -d ' ') hot spot nodes"
echo "- $(wc -l < "$RUN_ROOT/targets/topics.txt" | tr -d ' ') topics"
echo
echo "Agent prompt:"
echo "$RUN_ROOT/agent-prompt.md"
echo

if [[ "$RUN_AGENT" == "1" ]]; then
  echo "Launching Codex agent..."
  "$RUN_ROOT/run-codex.sh"
else
  echo "Prepared only. To launch the agent later, run:"
  echo "bash \"$RUN_ROOT/run-codex.sh\""
fi
