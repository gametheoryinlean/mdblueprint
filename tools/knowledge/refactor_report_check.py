"""Validate graph-refactor proposal reports."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.export import home_topic_for_node, leaf_topic_ids_for_node, topic_prefixes
from tools.knowledge.node_refs import NODE_REF_RE
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic


FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?(.*)", re.DOTALL)
MARKED_NODE_RE = re.compile(r"(?<![A-Za-z0-9_])node:([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)")
DOTTED_ID_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\b")

AGENT_NAME = "graph-refactor-proposer"
DECISIONS = frozenset({"proposals", "no_action", "needs_human_decision", "blocked"})
PROPOSAL_KINDS = frozenset({
    "remove-redundant-dependency",
    "add-missing-dependency",
    "formulation-impact-review",
    "move-primary-topic",
    "add-topic-membership",
    "merge-duplicate",
    "split-node",
    "generalize-node",
    "mark-lean-topic-divergent",
    "separate-proof-plan-route",
    "write-missing-node-request",
    "needs-human-review",
})
CLASSIFICATIONS = frozenset({
    "mechanical-safe",
    "semantic-review",
    "request-needed",
    "blocked",
})
BASELINE_VALUES = {
    "check": frozenset({"passed", "failed", "not_run"}),
    "lint": frozenset({"passed", "findings", "not_run"}),
    "stats": frozenset({"collected", "not_run"}),
}
REQUIRED_SECTIONS = [
    "Scope",
    "Deterministic Baseline",
    "Proposals",
    "Refinement Pass",
    "Generality Gate",
    "Formulation-Sensitive Impact",
    "Request Files",
    "Human Decisions",
]
PROPOSAL_COLUMNS = [
    "proposal_id",
    "kind",
    "classification",
    "targets",
    "action",
    "evidence",
    "risk",
    "validation",
]
FORMULATION_REQUIRED_KINDS = frozenset({
    "remove-redundant-dependency",
    "add-missing-dependency",
    "formulation-impact-review",
    "merge-duplicate",
    "split-node",
    "generalize-node",
    "separate-proof-plan-route",
})
GENERALITY_REQUIRED_KINDS = frozenset({
    "merge-duplicate",
    "split-node",
    "generalize-node",
    "move-primary-topic",
})
REQUEST_REQUIRED_KINDS = frozenset({
    "split-node",
    "generalize-node",
    "write-missing-node-request",
})


def _load_nodes(root: Path) -> tuple[set[str], set[str]]:
    nodes = []
    for subdir in ("nodes", "staged"):
        directory = root / subdir
        if directory.exists():
            nodes.extend(scan_directory(directory))

    node_ids = {node.id for node in nodes if node.id}
    topic_ids: set[str] = set()
    for node in nodes:
        for topic in [home_topic_for_node(node), *leaf_topic_ids_for_node(node)]:
            topic_ids.update(topic_prefixes(topic))
    return node_ids, topic_ids


def _diag(level: str, path: Path, message: str, *, code: str = "REFACTOR_REPORT") -> Diagnostic:
    return Diagnostic(level, "<refactor-report>", message, path, code=code)


def _load_report(path: Path) -> tuple[dict[str, Any], str, list[Diagnostic]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, "", [_diag("error", path, f"cannot read report: {exc}")]

    match = FRONTMATTER_RE.match(text)
    if match is None:
        return {}, text, [_diag("error", path, "missing YAML frontmatter")]

    fm_text, body = match.group(1), match.group(2)
    try:
        frontmatter = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return {}, body, [_diag("error", path, f"invalid YAML frontmatter: {exc}")]

    if not isinstance(frontmatter, dict):
        return {}, body, [_diag("error", path, "frontmatter must be a mapping")]
    return frontmatter, body, []


def _is_iso_datetime(value: Any) -> bool:
    if isinstance(value, datetime):
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _section_map(body: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[title.lower()] = body[start:end].strip()
    return sections


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip().strip("`") for cell in stripped.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _proposal_rows(section: str) -> tuple[list[dict[str, str]], list[str]]:
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], []

    columns = [cell.strip().strip("`").lower() for cell in _split_table_row(lines[0])]
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        cells = _split_table_row(line)
        if _is_separator_row(cells):
            continue
        padded = cells + [""] * max(0, len(columns) - len(cells))
        rows.append(dict(zip(columns, padded)))
    return rows, columns


def _marked_node_ids(text: str) -> set[str]:
    ids = {match.group(1) for match in NODE_REF_RE.finditer(text)}
    ids.update(match.group(1) for match in MARKED_NODE_RE.finditer(text))
    return ids


def _bare_dotted_ids(text: str) -> set[str]:
    skip_suffixes = (".md", ".json", ".py", ".html", ".yml", ".yaml", ".toml")
    return {
        match.group(0)
        for match in DOTTED_ID_RE.finditer(text)
        if not match.group(0).endswith(skip_suffixes)
        and not match.group(0).startswith("tools.")
    }


def _looks_empty_or_na(text: str) -> bool:
    normalized = re.sub(r"[\s.;:-]+", " ", text.strip().lower()).strip()
    return normalized in {"", "none", "n a", "na", "not applicable"}


def _validate_frontmatter(
    fm: dict[str, Any],
    path: Path,
    *,
    node_ids: set[str],
    topic_ids: set[str],
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []

    def err(message: str) -> None:
        diags.append(_diag("error", path, message))

    if fm.get("agent") != AGENT_NAME:
        err(f"agent must be {AGENT_NAME!r}")

    decision = fm.get("decision")
    if decision not in DECISIONS:
        err(f"decision must be one of {sorted(DECISIONS)}")

    if not _is_iso_datetime(fm.get("created_at")):
        err("created_at must be an ISO-8601 timestamp")

    inputs = fm.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        err("inputs must be a non-empty list")

    if not isinstance(fm.get("summary"), str) or not fm.get("summary", "").strip():
        err("summary must be a non-empty string")

    target = fm.get("target")
    if not isinstance(target, dict):
        err("target must be a mapping")
    else:
        if not target.get("knowledge_root"):
            err("target.knowledge_root is required")
        node_id = target.get("node_id")
        topic = target.get("topic")
        if node_id and node_id not in node_ids:
            err(f"target.node_id is not a loaded node: {node_id!r}")
        if topic and topic not in topic_ids:
            err(f"target.topic is not a loaded topic: {topic!r}")

    baseline = fm.get("baseline")
    if not isinstance(baseline, dict):
        err("baseline must be a mapping")
    else:
        for key, allowed in BASELINE_VALUES.items():
            value = baseline.get(key)
            if value not in allowed:
                err(f"baseline.{key} must be one of {sorted(allowed)}")

    impact = fm.get("formulation_impact")
    if not isinstance(impact, dict):
        err("formulation_impact must be a mapping")
    else:
        if not isinstance(impact.get("reviewed"), bool):
            err("formulation_impact.reviewed must be true or false")
        if not isinstance(impact.get("reason"), str) or not impact.get("reason", "").strip():
            err("formulation_impact.reason must be a non-empty string")

    return diags


def _validate_sections(body: str, path: Path) -> tuple[dict[str, str], list[Diagnostic]]:
    sections = _section_map(body)
    diags: list[Diagnostic] = []
    for section in REQUIRED_SECTIONS:
        key = section.lower()
        if key not in sections:
            diags.append(_diag("error", path, f"missing required section: ## {section}"))
        elif not sections[key].strip():
            diags.append(_diag("warning", path, f"section is empty: ## {section}"))
    return sections, diags


def _validate_target_cell(
    cell: str,
    *,
    path: Path,
    node_ids: set[str],
    topic_ids: set[str],
    row_id: str,
    field: str,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for node_id in sorted(_marked_node_ids(cell)):
        if node_id not in node_ids:
            diags.append(_diag(
                "error",
                path,
                f"{row_id} {field} references unknown node id {node_id!r}",
            ))

    for token in sorted(_bare_dotted_ids(cell) - _marked_node_ids(cell)):
        if token in node_ids or token in topic_ids:
            continue
        if token.startswith("docs."):
            continue
        diags.append(_diag(
            "error",
            path,
            f"{row_id} {field} mentions unknown node/topic id {token!r}",
        ))
    return diags


def _validate_proposals(
    fm: dict[str, Any],
    sections: dict[str, str],
    path: Path,
    *,
    node_ids: set[str],
    topic_ids: set[str],
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    rows, columns = _proposal_rows(sections.get("proposals", ""))

    if columns:
        missing = [column for column in PROPOSAL_COLUMNS if column not in columns]
        for column in missing:
            diags.append(_diag("error", path, f"proposal table is missing column {column!r}"))

    decision = fm.get("decision")
    if decision == "proposals" and not rows:
        diags.append(_diag("error", path, "decision is 'proposals' but proposal table has no rows"))
    if decision == "no_action" and rows:
        diags.append(_diag("warning", path, "decision is 'no_action' but proposal rows are present"))

    seen_ids: set[str] = set()
    proposal_kinds: set[str] = set()
    classifications: set[str] = set()

    for index, row in enumerate(rows, start=1):
        proposal_id = row.get("proposal_id", "").strip() or f"row {index}"
        if proposal_id in seen_ids:
            diags.append(_diag("error", path, f"duplicate proposal_id {proposal_id!r}"))
        seen_ids.add(proposal_id)
        if not re.fullmatch(r"refactor-\d{3,}", proposal_id):
            diags.append(_diag(
                "warning",
                path,
                f"{proposal_id} should use a stable id like refactor-001",
            ))

        for column in PROPOSAL_COLUMNS:
            if not row.get(column, "").strip():
                diags.append(_diag("error", path, f"{proposal_id} missing {column!r}"))

        kind = row.get("kind", "").strip()
        classification = row.get("classification", "").strip()
        proposal_kinds.add(kind)
        classifications.add(classification)
        if kind and kind not in PROPOSAL_KINDS:
            diags.append(_diag("error", path, f"{proposal_id} has invalid kind {kind!r}"))
        if classification and classification not in CLASSIFICATIONS:
            diags.append(_diag(
                "error",
                path,
                f"{proposal_id} has invalid classification {classification!r}",
            ))

        for field in ("targets", "evidence"):
            diags.extend(_validate_target_cell(
                row.get(field, ""),
                path=path,
                node_ids=node_ids,
                topic_ids=topic_ids,
                row_id=proposal_id,
                field=field,
            ))

    impact = fm.get("formulation_impact") if isinstance(fm.get("formulation_impact"), dict) else {}
    if proposal_kinds.intersection(FORMULATION_REQUIRED_KINDS) and impact.get("reviewed") is not True:
        diags.append(_diag(
            "error",
            path,
            "formulation_impact.reviewed must be true for dependency/content-changing proposals",
        ))

    generality_section = sections.get("generality gate", "")
    if proposal_kinds.intersection(GENERALITY_REQUIRED_KINDS) and _looks_empty_or_na(generality_section):
        diags.append(_diag(
            "error",
            path,
            "Generality Gate section must be substantive for merge/split/generalize/rehome proposals",
        ))

    request_section = sections.get("request files", "")
    needs_request = proposal_kinds.intersection(REQUEST_REQUIRED_KINDS) or "request-needed" in classifications
    if needs_request and _looks_empty_or_na(request_section):
        diags.append(_diag(
            "error",
            path,
            "Request Files section must describe required request files",
        ))

    return diags


def check_refactor_report(report_path: Path, knowledge_root: Path) -> list[Diagnostic]:
    """Return deterministic diagnostics for a graph-refactor report."""
    node_ids, topic_ids = _load_nodes(knowledge_root)
    fm, body, diags = _load_report(report_path)
    if diags:
        return diags

    diags.extend(_validate_frontmatter(
        fm,
        report_path,
        node_ids=node_ids,
        topic_ids=topic_ids,
    ))
    sections, section_diags = _validate_sections(body, report_path)
    diags.extend(section_diags)
    diags.extend(_validate_proposals(
        fm,
        sections,
        report_path,
        node_ids=node_ids,
        topic_ids=topic_ids,
    ))
    return diags


def _diagnostic_payload(diag: Diagnostic) -> dict[str, Any]:
    return {
        "level": diag.level,
        "node_id": diag.node_id,
        "message": diag.message,
        "file_path": str(diag.file_path) if diag.file_path else None,
        "code": diag.code,
        "related": list(diag.related),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a graph-refactor proposal report."
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)
    diags = check_refactor_report(args.report, args.knowledge_root)
    errors = [diag for diag in diags if diag.level == "error"]
    warnings = [diag for diag in diags if diag.level == "warning"]

    if args.json:
        print(json.dumps({
            "errors": len(errors),
            "warnings": len(warnings),
            "diagnostics": [_diagnostic_payload(diag) for diag in diags],
        }, indent=2, ensure_ascii=False))
    else:
        for diag in sorted(diags, key=lambda d: (d.level, d.message)):
            print(diag)
        print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
