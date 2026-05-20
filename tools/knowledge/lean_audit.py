"""Coordinator utilities for the Markdown/Lean alignment audit pipeline."""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import re
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.config import LeanConfig
from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_check import check_configured_lean_references
from tools.knowledge.lean_index import LeanIndex, index_lean_project
from tools.knowledge.models import Node


NODE_AUDIT_STATES = frozenset({
    "missing_lean",
    "lean_ref_broken",
    "lean_ref_ambiguous",
    "pending_alignment",
    "aligned",
    "minor_repair_possible",
    "major_revision_needed",
    "cannot_fix_without_hint",
    "needs_lean_generation",
})

REF_CHECKER_STATUSES = frozenset({"resolved", "broken", "ambiguous", "suspicious"})

DECLARATION_ROLES = frozenset({
    "primary_definition",
    "theorem_statement",
    "projection",
    "helper",
    "notation",
    "instance",
})

REPAIR_DECISIONS = frozenset({"small_fix", "large_revision", "cannot_fix", "needs_user_hint"})

_LARGE_REVISION_FIELDS = frozenset({
    "statement", "conclusion", "hypotheses", "definition",
    "proof", "uses", "lean_code", "theorem",
})


class LeanAuditError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class RefCheckerResult:
    node_id: str
    status: str
    declarations: list[dict[str, str]]
    notes: str
    raw: dict[str, Any]


@dataclasses.dataclass(frozen=True)
class RepairClassifierResult:
    node_id: str
    decision: str
    reason: str
    raw: dict[str, Any]


def determine_node_audit_state(
    node: Node,
    lean_config: LeanConfig,
    indexes: dict[str, LeanIndex],
) -> str:
    """Return the audit state string for one node."""
    if node.lean is None:
        return "missing_lean"

    diags = check_configured_lean_references([node], lean_config, indexes)
    problems = [d for d in diags if d.level in {"error", "warning"}]
    if problems:
        msgs = " ".join(d.message for d in problems)
        if "ambiguous" in msgs.lower():
            return "lean_ref_ambiguous"
        return "lean_ref_broken"

    if node.verification and node.verification.alignment == "aligned":
        return "aligned"
    return "pending_alignment"


def build_ref_checker_bundle(
    node: Node,
    lean_config: LeanConfig,
    indexes: dict[str, LeanIndex],
) -> dict[str, Any]:
    """Build a bounded bundle for the Lean Ref Checker subagent."""
    if node.lean is None:
        raise LeanAuditError(f"node {node.id!r} has no lean block")

    repo_id = node.lean.repository or lean_config.default_repository
    if repo_id is None or repo_id not in indexes:
        raise LeanAuditError(f"Lean repository not configured for node {node.id!r}")

    idx = indexes[repo_id]
    resolved: list[dict[str, Any]] = []
    for decl_name in node.lean.declarations:
        if decl_name in idx.declarations:
            decl = idx.declarations[decl_name]
            resolved.append({
                "declaration": decl.qualified_name,
                "status": "found",
                "kind": decl.kind,
                "signature": decl.signature,
                "has_sorry": decl.has_sorry,
                "source_url": decl.source_url,
            })
        else:
            candidates = [
                q for q in idx.declarations
                if q.endswith(f".{decl_name}") or q == decl_name
            ]
            resolved.append({
                "declaration": decl_name,
                "status": "not_found" if not candidates else "ambiguous",
                "candidates": candidates[:5],
                "signature": None,
                "kind": None,
            })

    return {
        "node": {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "lean": {
                "repository": repo_id,
                "modules": list(node.lean.modules),
                "declarations": list(node.lean.declarations),
            },
        },
        "resolved_declarations": resolved,
        "instructions": {
            "agent": "lean-ref-checker",
            "must_not_write_frontmatter": True,
            "must_not_set_status_or_alignment": True,
            "return_structured_output_only": True,
        },
    }


def validate_ref_checker_output(raw: dict[str, Any]) -> RefCheckerResult:
    """Validate output from the Lean Ref Checker subagent."""
    if not isinstance(raw, dict):
        raise LeanAuditError("ref checker output must be a mapping")
    if raw.get("agent") != "lean-ref-checker":
        raise LeanAuditError("agent must be 'lean-ref-checker'")
    node_id = raw.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise LeanAuditError("node_id must be a non-empty string")
    if "verification" in raw or "lean" in raw or "frontmatter" in raw:
        raise LeanAuditError(
            "ref checker output must not contain 'verification', 'lean', or 'frontmatter' keys"
        )
    status = raw.get("status")
    if status not in REF_CHECKER_STATUSES:
        raise LeanAuditError(f"status must be one of {', '.join(sorted(REF_CHECKER_STATUSES))}")
    declarations_raw = raw.get("declarations") or []
    if not isinstance(declarations_raw, list):
        raise LeanAuditError("declarations must be a list")
    parsed_decls: list[dict[str, str]] = []
    for item in declarations_raw:
        if not isinstance(item, dict):
            raise LeanAuditError("declarations entries must be mappings")
        decl = item.get("declaration")
        if not isinstance(decl, str) or not decl.strip():
            raise LeanAuditError("each declaration entry requires a non-empty 'declaration' string")
        role = item.get("role")
        if role is not None and role not in DECLARATION_ROLES:
            raise LeanAuditError(
                f"role {role!r} is not valid; must be one of {', '.join(sorted(DECLARATION_ROLES))}"
            )
        parsed_decls.append({"declaration": decl.strip(), "role": role or ""})
    notes = raw.get("notes") or ""
    if not isinstance(notes, str):
        raise LeanAuditError("notes must be a string")
    return RefCheckerResult(
        node_id=node_id.strip(),
        status=status,
        declarations=parsed_decls,
        notes=notes,
        raw=raw,
    )


def validate_repair_classifier_output(raw: dict[str, Any]) -> RepairClassifierResult:
    """Validate output from the Repair Classifier subagent."""
    if not isinstance(raw, dict):
        raise LeanAuditError("repair classifier output must be a mapping")
    if raw.get("agent") != "repair-classifier":
        raise LeanAuditError("agent must be 'repair-classifier'")
    node_id = raw.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise LeanAuditError("node_id must be a non-empty string")
    if "patch" in raw or "diff" in raw:
        raise LeanAuditError(
            "repair classifier must not produce 'patch' or 'diff' keys; classify only"
        )
    decision = raw.get("decision")
    if decision not in REPAIR_DECISIONS:
        raise LeanAuditError(
            f"decision must be one of {', '.join(sorted(REPAIR_DECISIONS))}"
        )
    proposed_changes = raw.get("proposed_changes") or []
    if isinstance(proposed_changes, list) and decision == "small_fix":
        for change in proposed_changes:
            if isinstance(change, dict):
                field = str(change.get("field", "")).lower()
                if field in _LARGE_REVISION_FIELDS:
                    raise LeanAuditError(
                        f"changes to {field!r} must be classified as 'large_revision', not 'small_fix'"
                    )
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise LeanAuditError("reason must be a non-empty string")
    return RepairClassifierResult(
        node_id=node_id.strip(),
        decision=decision,
        reason=reason.strip(),
        raw=raw,
    )


def _timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def _safe_ts(ts: str) -> str:
    return re.sub(r"[:+]", "_", ts)


def write_needs_lean_report(node_id: str, reason: str, requests_dir: Path) -> Path:
    """Write a needs-lean request report for a node with no lean block."""
    requests_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    path = requests_dir / f"{node_id.replace('.', '_')}_needs_lean_{_safe_ts(ts)}.md"
    lines = [
        "---",
        "agent: lean-audit-coordinator",
        f"node_id: {node_id}",
        "decision: needs_lean_generation",
        f'created_at: "{ts}"',
        "---",
        "",
        f"# Needs Lean: {node_id}",
        "",
        f"Reason: {reason}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ref_check_report(result: RefCheckerResult, reviews_dir: Path) -> Path:
    """Write a Lean ref check report produced by the ref checker subagent."""
    reviews_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    path = reviews_dir / f"{result.node_id.replace('.', '_')}_lean_ref_check_{_safe_ts(ts)}.md"
    lines = [
        "---",
        "agent: lean-ref-checker",
        f"node_id: {result.node_id}",
        f"status: {result.status}",
        f'created_at: "{ts}"',
        "---",
        "",
        f"# Lean Ref Check: {result.node_id}",
        "",
        "```yaml",
        yaml.safe_dump(result.raw, sort_keys=False).rstrip(),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_repair_report(result: RepairClassifierResult, reviews_dir: Path) -> Path:
    """Write a repair classification report produced by the repair classifier."""
    reviews_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    path = reviews_dir / f"{result.node_id.replace('.', '_')}_alignment_repair_{_safe_ts(ts)}.md"
    lines = [
        "---",
        "agent: alignment-repair",
        f"node_id: {result.node_id}",
        f"decision: {result.decision}",
        f'created_at: "{ts}"',
        "---",
        "",
        f"# Alignment Repair: {result.node_id}",
        "",
        "```yaml",
        yaml.safe_dump(result.raw, sort_keys=False).rstrip(),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def list_node_audit_states(knowledge_root: Path) -> list[dict[str, str]]:
    """Return audit states for all nodes in the knowledge base."""
    ctx = KnowledgeContext.load(knowledge_root, lean=False)
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    rows = []
    for node in ctx.nodes_by_id.values():
        state = determine_node_audit_state(node, ctx.config.lean, indexes)
        rows.append({"node_id": node.id, "kind": node.kind, "state": state})
    return sorted(rows, key=lambda r: (r["state"], r["node_id"]))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Lean audit coordinator utilities."
    )
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument(
        "--list-states", action="store_true",
        help="Print audit states for all nodes as JSON",
    )
    args = parser.parse_args(argv)

    if args.list_states:
        rows = list_node_audit_states(args.knowledge_root)
        print(json.dumps(rows, indent=2))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
