"""Orchestrate a deterministic refactor -> countercheck run scaffold."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from tools.knowledge.lean_countercheck import (
    build_countercheck_report,
    build_name_corpus,
    safe_countercheck_artifact_stem,
    write_countercheck_report,
)
from tools.knowledge.parser import scan_directory
from tools.knowledge.refactor_dry_run import build_refactor_dry_run
from tools.knowledge.refactor_report_check import check_refactor_report
from tools.knowledge.validator import Diagnostic


SEMANTIC_KIND_PRIORITY = {
    "formulation-impact-review": 10,
    "separate-proof-plan-route": 20,
    "merge-duplicate": 30,
    "split-node": 35,
    "generalize-node": 35,
    "mark-lean-topic-divergent": 40,
    "needs-human-review": 45,
    "add-missing-dependency": 50,
    "move-primary-topic": 60,
    "add-topic-membership": 65,
    "write-missing-node-request": 70,
    "remove-redundant-dependency": 80,
}
CLASSIFICATION_PRIORITY_ADJUSTMENT = {
    "semantic-review": -5,
    "request-needed": 5,
    "mechanical-safe": 15,
    "blocked": 50,
}
DRY_RUN_PRIORITY = 90
NODE_REF_RE = re.compile(r"(?:\[\[node:|(?<![A-Za-z0-9_])node:)([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)")
DOTTED_ID_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ECONCSLIB_ROOT = REPO_ROOT.parent / "EconCSLib"
DEFAULT_KNOWLEDGE_ROOT = DEFAULT_ECONCSLIB_ROOT / "docs" / "knowledge"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "runs" / "refactor-countercheck"
AgentRunner = Callable[..., dict[str, Any]]


class PipelineError(RuntimeError):
    """Raised when deterministic pipeline validation blocks the run."""


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def _diagnostic_payload(diag: Diagnostic) -> dict[str, Any]:
    return {
        "level": diag.level,
        "node_id": diag.node_id,
        "message": diag.message,
        "file_path": str(diag.file_path) if diag.file_path else None,
        "code": diag.code,
        "related": list(diag.related),
    }


def _copy_file(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _display_path(path: Path) -> str:
    relpath = os.path.relpath(path, REPO_ROOT)
    return relpath if not relpath.startswith(".." + os.sep + "..") else str(path)


def _section_map(markdown: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[title] = markdown[start:end].strip()
    return sections


def _body_without_frontmatter(text: str) -> str:
    match = re.match(r"\A---\n.*?\n---\n?(.*)", text, flags=re.DOTALL)
    return match.group(1) if match else text


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip().strip("`") for cell in stripped.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _proposal_rows(report_path: Path) -> list[dict[str, str]]:
    text = report_path.read_text(encoding="utf-8")
    sections = _section_map(_body_without_frontmatter(text))
    proposals = sections.get("proposals", "")
    lines = [line for line in proposals.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    columns = [cell.strip().lower() for cell in _split_table_row(lines[0])]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        cells = _split_table_row(line)
        if _is_separator_row(cells):
            continue
        padded = cells + [""] * max(0, len(columns) - len(cells))
        rows.append(dict(zip(columns, padded)))
    return rows


def _node_refs(text: str, loaded_ids: set[str]) -> set[str]:
    refs = set(NODE_REF_RE.findall(text))
    refs.update(token for token in DOTTED_ID_RE.findall(text) if token in loaded_ids)
    return refs


def _merge_candidate(
    candidates: dict[str, dict[str, Any]],
    node_id: str,
    *,
    source: str,
    priority: int,
    proposal_id: str | None = None,
    proposal_kind: str | None = None,
    classification: str | None = None,
    operation: dict[str, Any] | None = None,
) -> None:
    current = candidates.setdefault(
        node_id,
        {
            "node_id": node_id,
            "priority": priority,
            "sources": [],
            "proposal_ids": [],
            "proposal_kinds": [],
            "classifications": [],
            "operations": [],
        },
    )
    current["priority"] = min(current["priority"], priority)
    if source not in current["sources"]:
        current["sources"].append(source)
    if proposal_id and proposal_id not in current["proposal_ids"]:
        current["proposal_ids"].append(proposal_id)
    if proposal_kind and proposal_kind not in current["proposal_kinds"]:
        current["proposal_kinds"].append(proposal_kind)
    if classification and classification not in current["classifications"]:
        current["classifications"].append(classification)
    if operation is not None:
        current["operations"].append(operation)


def _report_candidates(report_path: Path, loaded_ids: set[str]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for row in _proposal_rows(report_path):
        proposal_id = row.get("proposal_id", "").strip() or None
        kind = row.get("kind", "").strip() or None
        classification = row.get("classification", "").strip() or None
        priority = SEMANTIC_KIND_PRIORITY.get(kind or "", 75)
        priority += CLASSIFICATION_PRIORITY_ADJUSTMENT.get(classification or "", 0)
        refs = _node_refs(" ".join([row.get("targets", ""), row.get("evidence", "")]), loaded_ids)
        for node_id in sorted(refs):
            _merge_candidate(
                candidates,
                node_id,
                source="refactor-report",
                priority=priority,
                proposal_id=proposal_id,
                proposal_kind=kind,
                classification=classification,
            )
    return candidates


def _dry_run_candidates(dry_run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for item in dry_run.get("changed_nodes", []):
        node_id = item.get("node_id")
        if isinstance(node_id, str) and node_id:
            _merge_candidate(candidates, node_id, source="dry-run-changed", priority=DRY_RUN_PRIORITY)
    for result in dry_run.get("operations", []):
        if result.get("status") != "applied":
            continue
        operation = result.get("operation") if isinstance(result.get("operation"), dict) else {}
        node_id = operation.get("node_id")
        if isinstance(node_id, str) and node_id:
            _merge_candidate(
                candidates,
                node_id,
                source="dry-run-operation",
                priority=DRY_RUN_PRIORITY,
                operation=operation,
            )
    for item in dry_run.get("removed_nodes", []):
        node_id = item.get("id")
        if isinstance(node_id, str) and node_id:
            _merge_candidate(candidates, node_id, source="dry-run-removed", priority=DRY_RUN_PRIORITY + 5)
    return candidates


def _combined_candidates(
    *,
    report_path: Path | None,
    dry_run: dict[str, Any] | None,
    loaded_ids: set[str],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source in (
        _report_candidates(report_path, loaded_ids) if report_path else {},
        _dry_run_candidates(dry_run) if dry_run else {},
    ):
        for node_id, candidate in source.items():
            for source_name in candidate["sources"]:
                _merge_candidate(
                    merged,
                    node_id,
                    source=source_name,
                    priority=int(candidate["priority"]),
                )
            target = merged[node_id]
            for key in ("proposal_ids", "proposal_kinds", "classifications"):
                for value in candidate.get(key, []):
                    if value not in target[key]:
                        target[key].append(value)
            target["operations"].extend(candidate.get("operations", []))
    return sorted(merged.values(), key=lambda item: (item["priority"], item["node_id"]))


def _load_nodes(knowledge_root: Path, *, include_staged: bool) -> dict[str, Any]:
    nodes = []
    nodes_dir = knowledge_root / "nodes"
    staged_dir = knowledge_root / "staged"
    if nodes_dir.exists():
        nodes.extend(scan_directory(nodes_dir))
    if include_staged and staged_dir.exists():
        nodes.extend(scan_directory(staged_dir))
    return {node.id: node for node in nodes if node.id}


def _module_path(source_root: Path, module: str) -> Path:
    return source_root.joinpath(*module.split(".")).with_suffix(".lean")


def _countercheck_pairs(
    candidates: list[dict[str, Any]],
    *,
    nodes_by_id: dict[str, Any],
    lean_source_root: Path,
    max_pairs: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidates:
        node_id = candidate["node_id"]
        node = nodes_by_id.get(node_id)
        if node is None:
            skipped.append({**candidate, "reason": "node is not loaded in the selected admitted/staged scope"})
            continue
        if node.file_path is None:
            skipped.append({**candidate, "reason": "node has no source file path"})
            continue
        if node.lean is None:
            skipped.append({**candidate, "reason": "node has no lean metadata"})
            continue
        if not node.lean.modules:
            skipped.append({**candidate, "reason": "node has no lean.modules"})
            continue
        if not node.lean.declarations:
            skipped.append({**candidate, "reason": "node has no lean.declarations"})
            continue
        added = 0
        missing_modules: list[str] = []
        for module in node.lean.modules:
            lean_file = _module_path(lean_source_root, module)
            if not lean_file.exists():
                missing_modules.append(module)
                continue
            if len(pairs) >= max_pairs:
                skipped.append({**candidate, "reason": "max-countercheck-pairs limit reached"})
                return pairs, skipped
            pairs.append({
                "node_id": node_id,
                "node_file": str(node.file_path),
                "lean_file": str(lean_file),
                "module": module,
                "declarations": list(node.lean.declarations),
                "priority": candidate["priority"],
                "sources": list(candidate["sources"]),
                "proposal_ids": list(candidate["proposal_ids"]),
                "proposal_kinds": list(candidate["proposal_kinds"]),
                "classifications": list(candidate["classifications"]),
            })
            added += 1
        if added == 0:
            skipped.append({
                **candidate,
                "reason": "no lean.modules resolved to files",
                "missing_modules": missing_modules,
            })
    return pairs, skipped


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _run_counterchecks(
    pairs: list[dict[str, Any]],
    *,
    lean_source_root: Path,
    lean_corpus_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    counter_dir = output_dir / "counterchecks"
    review_dir = output_dir / "reviews"
    counter_dir.mkdir(parents=True, exist_ok=True)
    corpus_names = build_name_corpus(lean_corpus_root, source_root=lean_source_root)
    reports: list[dict[str, Any]] = []
    used_stems: dict[str, int] = {}
    for pair in pairs:
        report = build_countercheck_report(
            node_file=Path(pair["node_file"]),
            lean_file=Path(pair["lean_file"]),
            source_root=lean_source_root,
            corpus_root=lean_corpus_root,
            corpus_names=corpus_names,
        )
        base_stem = safe_countercheck_artifact_stem(
            report.node_id,
            pair["lean_file"],
            module=pair.get("module") if isinstance(pair.get("module"), str) else None,
        )
        stem_count = used_stems.get(base_stem, 0)
        used_stems[base_stem] = stem_count + 1
        stem = base_stem if stem_count == 0 else f"{base_stem}__{stem_count + 1}"
        report_path = counter_dir / f"{stem}.json"
        _write_json(report_path, report.raw)
        review_path = write_countercheck_report(report, review_dir, filename_stem=f"{stem}_lean_countercheck")
        reports.append({
            "node_id": report.node_id,
            "node_file": pair["node_file"],
            "lean_file": pair["lean_file"],
            "countercheck_json": str(report_path),
            "review_path": str(review_path),
            "missing_declarations": report.missing_declarations,
            "extra_declarations": report.extra_declarations,
            "missing_uses": report.missing_uses,
            "extra_uses": report.extra_uses,
        })
    summary = {
        "pairs": len(pairs),
        "corpus_names": len(corpus_names),
        "nodes_with_missing_decls": sum(bool(r["missing_declarations"]) for r in reports),
        "nodes_with_extra_decls": sum(bool(r["extra_declarations"]) for r in reports),
        "nodes_with_missing_uses": sum(bool(r["missing_uses"]) for r in reports),
        "nodes_with_extra_uses": sum(bool(r["extra_uses"]) for r in reports),
        "reports": reports,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def _codex_command_parts(codex_cmd: str | Sequence[str]) -> list[str]:
    if isinstance(codex_cmd, str):
        parts = shlex.split(codex_cmd)
    else:
        parts = list(codex_cmd)
    if not parts:
        raise PipelineError("codex command is empty")
    return parts


def _run_codex_agent(
    *,
    stage: str,
    prompt_path: Path,
    last_message_path: Path,
    events_path: Path,
    stderr_path: Path,
    knowledge_root: Path,
    lean_source_root: Path,
    codex_cmd: str | Sequence[str],
    codex_model: str | None = None,
) -> dict[str, Any]:
    last_message_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    run_dir = prompt_path.parent.parent.resolve()
    add_dirs = []
    for path in (lean_source_root.resolve(), knowledge_root.resolve(), run_dir):
        if path == REPO_ROOT or path.is_relative_to(REPO_ROOT):
            continue
        if path not in add_dirs:
            add_dirs.append(path)

    command = _codex_command_parts(codex_cmd) + [
        "exec",
        "-C",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
        "--json",
        "-o",
        str(last_message_path),
    ]
    for path in add_dirs:
        command.extend(["--add-dir", str(path)])
    if codex_model:
        command.extend(["-m", codex_model])
    command.append("-")

    try:
        with events_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            completed = subprocess.run(
                command,
                input=prompt_path.read_text(encoding="utf-8"),
                stdout=stdout,
                stderr=stderr,
                text=True,
                cwd=REPO_ROOT,
                check=False,
            )
    except FileNotFoundError as exc:
        raise PipelineError(f"failed to run Codex command {command[0]!r}: {exc}") from exc

    return {
        "stage": stage,
        "returncode": completed.returncode,
        "command": command,
        "prompt_path": str(prompt_path),
        "last_message_path": str(last_message_path),
        "events_path": str(events_path),
        "stderr_path": str(stderr_path),
    }


def _write_prompt_files(
    run_dir: Path,
    *,
    knowledge_root: Path,
    lean_source_root: Path,
    include_staged: bool,
) -> dict[str, str]:
    prompt_dir = run_dir / "prompts"
    script_dir = run_dir / "scripts"
    log_dir = run_dir / "logs"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    script_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    refactor_prompt = prompt_dir / "refactor-agent.md"
    staged_scope = "admitted+staged" if include_staged else "admitted"
    refactor_prompt.write_text(
        "\n".join([
            "# Graph Refactor Agent Run",
            "",
            "Use `skills/mdblueprint-graph-refactor-review/SKILL.md`.",
            f"Knowledge root: `{_display_path(knowledge_root)}`",
            f"Scope mode: `{staged_scope}`.",
            f"Pass `--include-staged`: `{str(include_staged).lower()}`.",
            "",
            f"Write the refactor report to `{_display_path(run_dir / 'reports' / 'refactor-report.md')}`.",
            f"Write the dry-run plan to `{_display_path(run_dir / 'dry-runs' / 'refactor-plan.yml')}`.",
            "If no concrete operation survives refinement, write a valid dry-run plan with `operations: []`.",
            "Do not edit admitted or staged knowledge files.",
            "",
        ]),
        encoding="utf-8",
    )

    adjudicator_prompt = prompt_dir / "adjudicator.md"
    adjudicator_prompt.write_text(
        "\n".join([
            "# Lean Adjudicator Run",
            "",
            "Use `skills/mdblueprint-lean-adjudicate/SKILL.md`.",
            "Use `skills/mdblueprint-lean-adjudicate/references/agent-config.toml` for defaults.",
            f"Knowledge root: `{_display_path(knowledge_root)}`",
            f"Lean source root: `{_display_path(lean_source_root)}`",
            "",
            "Inputs, when present:",
            f"- refactor report: `{_display_path(run_dir / 'reports' / 'refactor-report.md')}`",
            f"- dry-run JSON: `{_display_path(run_dir / 'dry-runs' / 'refactor-dry-run.json')}`",
            f"- countercheck pairs: `{_display_path(run_dir / 'countercheck' / 'pairs.json')}`",
            f"- skipped candidates: `{_display_path(run_dir / 'countercheck' / 'skipped.json')}`",
            f"- countercheck summary: `{_display_path(run_dir / 'countercheck' / 'summary.json')}`",
            "",
            f"Write the adjudication report to `{_display_path(run_dir / 'adjudication' / 'adjudication-report.md')}`.",
            "Do not edit admitted or staged knowledge files.",
            "",
        ]),
        encoding="utf-8",
    )

    scripts: dict[str, str] = {}
    for name, prompt in (
        ("run-refactor-agent.sh", refactor_prompt),
        ("run-adjudicator.sh", adjudicator_prompt),
    ):
        script = script_dir / name
        last_message_name = name.replace(".sh", "-last-message.md")
        events_name = name.replace(".sh", "-events.jsonl")
        script.write_text(
            "\n".join([
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
                'RUN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
                'if [[ -n "${MDBLUEPRINT_REPO_ROOT:-}" ]]; then',
                '  REPO_ROOT="$MDBLUEPRINT_REPO_ROOT"',
                "else",
                '  if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1; then',
                '    REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"',
                "  else",
                '    REPO_ROOT="$(git rev-parse --show-toplevel)"',
                "  fi",
                "fi",
                'LEAN_SOURCE_ROOT="${MDBLUEPRINT_LEAN_SOURCE_ROOT:-$REPO_ROOT/../EconCSLib}"',
                'KNOWLEDGE_ROOT="${MDBLUEPRINT_KNOWLEDGE_ROOT:-$LEAN_SOURCE_ROOT/docs/knowledge}"',
                'CODEX_BIN="${CODEX_BIN:-codex}"',
                "MODEL_ARGS=()",
                'if [[ -n "${CODEX_MODEL:-}" ]]; then',
                '  MODEL_ARGS=(-m "$CODEX_MODEL")',
                "fi",
                "ADD_DIR_ARGS=()",
                'for EXTRA_DIR in "$LEAN_SOURCE_ROOT" "$KNOWLEDGE_ROOT" "$RUN_DIR"; do',
                '  case "$EXTRA_DIR" in',
                '    "$REPO_ROOT"|"$REPO_ROOT"/*) ;;',
                '    *) ADD_DIR_ARGS+=(--add-dir "$EXTRA_DIR") ;;',
                "  esac",
                "done",
                f'PROMPT="$RUN_DIR/prompts/{prompt.name}"',
                f'LAST_MESSAGE="$RUN_DIR/logs/{last_message_name}"',
                f'EVENTS="$RUN_DIR/logs/{events_name}"',
                '"$CODEX_BIN" exec -C "$REPO_ROOT" --sandbox workspace-write --json -o "$LAST_MESSAGE" "${ADD_DIR_ARGS[@]}" "${MODEL_ARGS[@]}" - < "$PROMPT" | tee "$EVENTS"',
                "",
            ]),
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        scripts[name] = str(script)
    return scripts


def _write_summary(run_dir: Path, result: dict[str, Any]) -> Path:
    lines = [
        "# Refactor Countercheck Run",
        "",
        f"- run directory: `{run_dir}`",
        f"- knowledge root: `{result['knowledge_root']}`",
        f"- Lean source root: `{result['lean_source_root']}`",
        f"- include staged: `{str(result['include_staged']).lower()}`",
        f"- refactor agent run: `{str(result['refactor_agent_ran']).lower()}`",
        f"- candidates: `{result['candidate_count']}`",
        f"- countercheck pairs: `{result['pair_count']}`",
        f"- skipped candidates: `{result['skipped_count']}`",
        f"- countercheck run: `{str(result['countercheck_ran']).lower()}`",
        f"- adjudicator run: `{str(result['adjudicator_ran']).lower()}`",
        "",
        "Key files:",
        "",
    ]
    for key in (
        "metadata",
        "refactor_report",
        "dry_run_json",
        "candidates_json",
        "pairs_json",
        "skipped_json",
        "countercheck_summary",
        "adjudication_report",
        "adjudicator_prompt",
    ):
        value = result.get("paths", {}).get(key)
        if value:
            lines.append(f"- {key}: `{value}`")
    path = run_dir / "SUMMARY.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_refactor_countercheck_run(
    *,
    knowledge_root: Path,
    lean_source_root: Path,
    output_root: Path,
    refactor_report: Path | None = None,
    dry_run_plan: Path | None = None,
    lean_corpus_root: Path | None = None,
    include_staged: bool = False,
    max_countercheck_pairs: int = 16,
    timestamp: str | None = None,
    prepare_only: bool = False,
    run_refactor_agent: bool = False,
    run_countercheck: bool = True,
    run_adjudicator: bool = False,
    allow_dry_run_errors: bool = False,
    codex_cmd: str | Sequence[str] = "codex",
    codex_model: str | None = None,
    agent_runner: AgentRunner | None = None,
) -> dict[str, Any]:
    if prepare_only and (run_refactor_agent or run_adjudicator):
        raise PipelineError("prepare-only cannot run agent stages")
    if run_refactor_agent and (refactor_report is not None or dry_run_plan is not None):
        raise PipelineError("do not pass --refactor-report or --dry-run-plan when running the refactor agent")

    knowledge_root = knowledge_root.resolve()
    lean_source_root = lean_source_root.resolve()
    output_root = output_root.resolve()
    lean_corpus_root = lean_corpus_root.resolve() if lean_corpus_root else lean_source_root

    run_id = timestamp or _timestamp()
    run_dir = output_root / run_id
    if run_dir.exists():
        raise PipelineError(f"run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    (run_dir / "reports").mkdir()
    (run_dir / "dry-runs").mkdir()
    (run_dir / "countercheck").mkdir()
    (run_dir / "adjudication").mkdir()

    scripts = _write_prompt_files(
        run_dir,
        knowledge_root=knowledge_root,
        lean_source_root=lean_source_root,
        include_staged=include_staged,
    )
    nodes_by_id = _load_nodes(knowledge_root, include_staged=include_staged)
    report_copy: Path | None = None
    plan_copy: Path | None = None
    dry_run_json: Path | None = None
    dry_run: dict[str, Any] | None = None
    report_diagnostics: list[dict[str, Any]] = []
    agent_results: list[dict[str, Any]] = []
    adjudication_report: Path | None = None
    runner = agent_runner or _run_codex_agent

    if refactor_report is not None:
        report_copy = _copy_file(refactor_report, run_dir / "reports" / "refactor-report.md")
    if dry_run_plan is not None:
        plan_copy = _copy_file(dry_run_plan, run_dir / "dry-runs" / "refactor-plan.yml")

    if run_refactor_agent:
        refactor_result = runner(
            stage="refactor",
            prompt_path=run_dir / "prompts" / "refactor-agent.md",
            last_message_path=run_dir / "logs" / "run-refactor-agent-last-message.md",
            events_path=run_dir / "logs" / "run-refactor-agent-events.jsonl",
            stderr_path=run_dir / "logs" / "run-refactor-agent.stderr",
            knowledge_root=knowledge_root,
            lean_source_root=lean_source_root,
            codex_cmd=codex_cmd,
            codex_model=codex_model,
        )
        agent_results.append(refactor_result)
        if int(refactor_result.get("returncode", 1)) != 0:
            raise PipelineError("refactor agent failed; see run-refactor-agent stderr/events logs")
        report_copy = run_dir / "reports" / "refactor-report.md"
        plan_copy = run_dir / "dry-runs" / "refactor-plan.yml"
        missing_outputs = [path for path in (report_copy, plan_copy) if not path.exists()]
        if missing_outputs:
            joined = ", ".join(str(path) for path in missing_outputs)
            raise PipelineError(f"refactor agent did not produce required output(s): {joined}")

    if not prepare_only and report_copy is not None:
        diagnostics = check_refactor_report(report_copy, knowledge_root)
        report_diagnostics = [_diagnostic_payload(diag) for diag in diagnostics]
        _write_json(run_dir / "reports" / "refactor-report-check.json", report_diagnostics)
        errors = [diag for diag in diagnostics if diag.level == "error"]
        if errors:
            raise PipelineError(f"refactor report validation failed with {len(errors)} error(s)")

    if not prepare_only and plan_copy is not None:
        dry_run = build_refactor_dry_run(knowledge_root, plan_copy, include_staged=include_staged)
        dry_run_json = run_dir / "dry-runs" / "refactor-dry-run.json"
        _write_json(dry_run_json, dry_run)
        if dry_run["would_introduce_errors"] and not allow_dry_run_errors:
            raise PipelineError("dry run would introduce errors; pass --allow-dry-run-errors to continue")

    candidates = (
        []
        if prepare_only
        else _combined_candidates(
            report_path=report_copy,
            dry_run=dry_run,
            loaded_ids=set(nodes_by_id),
        )
    )
    pairs, skipped = _countercheck_pairs(
        candidates,
        nodes_by_id=nodes_by_id,
        lean_source_root=lean_source_root,
        max_pairs=max_countercheck_pairs,
    ) if candidates else ([], [])

    candidates_json = _write_json(run_dir / "countercheck" / "candidates.json", candidates)
    pairs_json = _write_json(run_dir / "countercheck" / "pairs.json", pairs)
    skipped_json = _write_json(run_dir / "countercheck" / "skipped.json", skipped)

    countercheck_summary: dict[str, Any] | None = None
    countercheck_summary_path: Path | None = None
    if not prepare_only and run_countercheck:
        countercheck_summary_path = run_dir / "countercheck" / "summary.json"
        if pairs:
            countercheck_summary = _run_counterchecks(
                pairs,
                lean_source_root=lean_source_root,
                lean_corpus_root=lean_corpus_root,
                output_dir=run_dir / "countercheck",
            )
        else:
            countercheck_summary = {
                "pairs": 0,
                "corpus_names": 0,
                "nodes_with_missing_decls": 0,
                "nodes_with_extra_decls": 0,
                "nodes_with_missing_uses": 0,
                "nodes_with_extra_uses": 0,
                "reports": [],
            }
            _write_json(countercheck_summary_path, countercheck_summary)

    if run_adjudicator:
        adjudicator_result = runner(
            stage="adjudicator",
            prompt_path=run_dir / "prompts" / "adjudicator.md",
            last_message_path=run_dir / "logs" / "run-adjudicator-last-message.md",
            events_path=run_dir / "logs" / "run-adjudicator-events.jsonl",
            stderr_path=run_dir / "logs" / "run-adjudicator.stderr",
            knowledge_root=knowledge_root,
            lean_source_root=lean_source_root,
            codex_cmd=codex_cmd,
            codex_model=codex_model,
        )
        agent_results.append(adjudicator_result)
        if int(adjudicator_result.get("returncode", 1)) != 0:
            raise PipelineError("adjudicator agent failed; see run-adjudicator stderr/events logs")
        adjudication_report = run_dir / "adjudication" / "adjudication-report.md"
        if not adjudication_report.exists():
            raise PipelineError(f"adjudicator did not produce required output: {adjudication_report}")

    paths = {
        "metadata": str(run_dir / "metadata.json"),
        "refactor_report": str(report_copy) if report_copy else None,
        "dry_run_plan": str(plan_copy) if plan_copy else None,
        "dry_run_json": str(dry_run_json) if dry_run_json else None,
        "candidates_json": str(candidates_json),
        "pairs_json": str(pairs_json),
        "skipped_json": str(skipped_json),
        "countercheck_summary": str(countercheck_summary_path) if countercheck_summary_path else None,
        "adjudication_report": str(adjudication_report) if adjudication_report else None,
        "refactor_prompt": str(run_dir / "prompts" / "refactor-agent.md"),
        "adjudicator_prompt": str(run_dir / "prompts" / "adjudicator.md"),
        "run_refactor_agent": scripts.get("run-refactor-agent.sh"),
        "run_adjudicator": scripts.get("run-adjudicator.sh"),
    }
    result = {
        "kind": "mdblueprint-refactor-countercheck-run",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "knowledge_root": str(knowledge_root),
        "lean_source_root": str(lean_source_root),
        "lean_corpus_root": str(lean_corpus_root),
        "include_staged": include_staged,
        "prepare_only": prepare_only,
        "refactor_agent_ran": run_refactor_agent,
        "candidate_count": len(candidates),
        "pair_count": len(pairs),
        "skipped_count": len(skipped),
        "countercheck_ran": countercheck_summary is not None,
        "adjudicator_ran": run_adjudicator,
        "agent_results": agent_results,
        "report_diagnostics": report_diagnostics,
        "dry_run_summary": dry_run.get("summary") if dry_run else None,
        "countercheck_summary": countercheck_summary,
        "paths": paths,
    }
    _write_json(run_dir / "metadata.json", result)
    summary_path = _write_summary(run_dir, result)
    result["paths"]["summary"] = str(summary_path)
    _write_json(run_dir / "metadata.json", result)
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdblueprint-refactor-countercheck",
        description="Run an orchestrated refactor -> Lean countercheck -> adjudication pipeline.",
    )
    parser.add_argument(
        "--knowledge-root",
        type=Path,
        default=DEFAULT_KNOWLEDGE_ROOT,
        help="Knowledge root. Defaults to ../EconCSLib/docs/knowledge relative to this repository.",
    )
    parser.add_argument(
        "--lean-source-root",
        type=Path,
        default=DEFAULT_ECONCSLIB_ROOT,
        help="Lean source root. Defaults to ../EconCSLib relative to this repository.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--refactor-report", type=Path)
    parser.add_argument("--dry-run-plan", type=Path)
    parser.add_argument("--lean-corpus-root", type=Path)
    parser.add_argument("--include-staged", action="store_true")
    parser.add_argument("--max-countercheck-pairs", type=int, default=16)
    parser.add_argument("--timestamp")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument(
        "--run-refactor-agent",
        action="store_true",
        help="Force a fresh refactor-agent pass. By default this is enabled when no report or plan is provided.",
    )
    parser.add_argument(
        "--skip-refactor-agent",
        action="store_true",
        help="Do not run the refactor agent; use this with --refactor-report and/or --dry-run-plan.",
    )
    parser.add_argument("--skip-countercheck", action="store_true")
    parser.add_argument("--skip-adjudicator", action="store_true")
    parser.add_argument("--allow-dry-run-errors", action="store_true")
    parser.add_argument("--codex-cmd", default="codex", help="Codex executable or command prefix for agent stages.")
    parser.add_argument("--codex-model", help="Optional Codex model passed with -m during agent stages.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.run_refactor_agent and args.skip_refactor_agent:
        parser.error("--run-refactor-agent and --skip-refactor-agent are mutually exclusive")
    if args.run_refactor_agent and (args.refactor_report is not None or args.dry_run_plan is not None):
        parser.error("--run-refactor-agent cannot be combined with --refactor-report or --dry-run-plan")

    run_refactor_agent = (
        not args.prepare_only
        and not args.skip_refactor_agent
        and (args.run_refactor_agent or (args.refactor_report is None and args.dry_run_plan is None))
    )
    if (
        not args.prepare_only
        and not run_refactor_agent
        and args.refactor_report is None
        and args.dry_run_plan is None
    ):
        parser.error("no refactor artifacts provided; omit --skip-refactor-agent or pass --prepare-only")

    try:
        result = build_refactor_countercheck_run(
            knowledge_root=args.knowledge_root,
            lean_source_root=args.lean_source_root,
            output_root=args.output_root,
            refactor_report=args.refactor_report,
            dry_run_plan=args.dry_run_plan,
            lean_corpus_root=args.lean_corpus_root,
            include_staged=args.include_staged,
            max_countercheck_pairs=args.max_countercheck_pairs,
            timestamp=args.timestamp,
            prepare_only=args.prepare_only,
            run_refactor_agent=run_refactor_agent,
            run_countercheck=not args.skip_countercheck,
            run_adjudicator=not args.prepare_only and not args.skip_countercheck and not args.skip_adjudicator,
            allow_dry_run_errors=args.allow_dry_run_errors,
            codex_cmd=args.codex_cmd,
            codex_model=args.codex_model,
        )
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
