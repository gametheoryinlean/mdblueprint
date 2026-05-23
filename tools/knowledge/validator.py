"""Schema validation for knowledge nodes."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.knowledge.models import (
    ADMITTED_STATUSES,
    DEFINITION_KINDS,
    FORBIDDEN_HEADINGS,
    MATH_KINDS,
    STAGED_STATUSES,
    STATEMENT_KINDS,
    VALID_ALIGNMENT_VALUES,
    VALID_DEFINITION_VALUES,
    VALID_KINDS,
    VALID_LOCATOR_FORMATS,
    VALID_PLAN_STATUSES,
    VALID_PROOF_VALUES,
    VALID_STATEMENT_VALUES,
    VALID_STATUSES,
    Node,
    SourceLibraryEntry,
)

_SOURCE_REQUIRED_KINDS = DEFINITION_KINDS | STATEMENT_KINDS


@dataclass
class Diagnostic:
    level: str  # "error", "warning", or "info"
    node_id: str
    message: str
    file_path: Path | None = None
    code: str | None = None
    related: tuple[str, ...] = ()

    def __str__(self) -> str:
        loc = f"{self.file_path} ({self.node_id})" if self.file_path else self.node_id
        code_segment = f"[{self.code}]" if self.code else ""
        return f"[{self.level.upper()}]{code_segment} {loc}: {self.message}"


def _heading_re():
    return re.compile(r"^##\s+(.+)$", re.MULTILINE)


def validate_node(
    node: Node,
    *,
    is_staged_dir: bool = False,
    project_library: dict[str, SourceLibraryEntry] | None = None,
    require_source_spans: bool = False,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    nid = node.id or "<no-id>"
    fp = node.file_path

    def err(msg: str) -> None:
        diags.append(Diagnostic("error", nid, msg, fp))

    def warn(msg: str) -> None:
        diags.append(Diagnostic("warning", nid, msg, fp))

    # Required fields for all nodes
    if not node.id:
        err("missing required field: id")
    if not node.title:
        err("missing required field: title")
    if not node.kind:
        err("missing required field: kind")
    elif node.kind not in VALID_KINDS:
        err(f"invalid kind: {node.kind!r}")
    if not node.status:
        err("missing required field: status")
    elif node.status not in VALID_STATUSES:
        err(f"invalid status: {node.status!r}")

    # Proof plans attach to a mathematical target. They are not ordinary uses edges.
    if node.kind == "proof-plan":
        if not node.target:
            err("proof-plan target is required")
        elif node.target == node.id:
            err("proof-plan target cannot be itself")
        if node.plan_status is not None and node.plan_status not in VALID_PLAN_STATUSES:
            err(f"invalid plan_status value: {node.plan_status!r}")
    else:
        if node.target is not None:
            err("target is only valid for proof-plan nodes")
        if node.plan_status is not None:
            err("plan_status is only valid for proof-plan nodes")

    # Directory-status consistency
    if is_staged_dir and node.status in ADMITTED_STATUSES:
        err(f"node in staged/ has admitted status: {node.status!r}")
    if not is_staged_dir and node.status in STAGED_STATUSES:
        err(f"node in nodes/ has staged status: {node.status!r}")

    # Verification field applicability
    v = node.verification
    if v is not None:
        if v.statement is not None and v.definition is not None:
            err("verification has both 'statement' and 'definition'; use one per kind")
        if v.statement is not None:
            if node.kind in DEFINITION_KINDS:
                warn(f"kind {node.kind!r} should use 'definition' not 'statement' in verification")
            if v.statement not in VALID_STATEMENT_VALUES:
                err(f"invalid verification.statement value: {v.statement!r}")
        if v.definition is not None:
            if node.kind in STATEMENT_KINDS:
                warn(f"kind {node.kind!r} should use 'statement' not 'definition' in verification")
            if v.definition not in VALID_DEFINITION_VALUES:
                err(f"invalid verification.definition value: {v.definition!r}")
        if v.proof is not None and v.proof not in VALID_PROOF_VALUES:
            err(f"invalid verification.proof value: {v.proof!r}")
        if v.alignment is not None and v.alignment not in VALID_ALIGNMENT_VALUES:
            err(f"invalid verification.alignment value: {v.alignment!r}")
        if v.alignment is not None and node.lean is None:
            if node.status in ADMITTED_STATUSES:
                err("verification.alignment requires a lean section")
            else:
                warn("verification.alignment requires a lean section before admission")

    # Source span artifact binding
    src = node.source
    if src is not None:
        artifact_ids = {a.id for a in src.artifacts}
        library_ids = set(project_library.keys()) if project_library else set()
        known_ids = artifact_ids | library_ids
        for span in src.spans:
            if span.artifact is not None and span.artifact not in known_ids:
                err(f"source span references unknown artifact: {span.artifact!r}")
            if span.format is not None and span.format not in VALID_LOCATOR_FORMATS:
                warn(f"unknown source span format: {span.format!r}")

    # Lean section for external-theorem
    if node.kind == "external-theorem":
        if node.lean is None or not node.lean.modules or not node.lean.declarations:
            err("external-theorem must have lean.modules and lean.declarations filled")

    if node.status in {"formalized", "proved"}:
        if node.lean is None or not node.lean.modules or not node.lean.declarations:
            err(f"{node.status} node must have lean.modules and lean.declarations filled")

    # Forbidden headings in body
    for m in _heading_re().finditer(node.body):
        heading = m.group(1).strip().lower()
        if heading in FORBIDDEN_HEADINGS:
            err(f"forbidden operational heading in body: {m.group(1).strip()!r}")

    # Admitted-only checks
    if node.status in ADMITTED_STATUSES and not is_staged_dir:
        if not node.uses and node.uses != []:
            warn("admitted node missing 'uses' field")

    # Source spans required by project config
    if require_source_spans and node.kind in _SOURCE_REQUIRED_KINDS:
        if node.source is None or not node.source.spans:
            warn(f"math node of kind {node.kind!r} has no source.spans (project requires sources)")

    # Topic membership consistency
    if node.topics:
        for t in node.topics:
            if not isinstance(t, str) or not t.strip():
                err("topics entries must be non-empty strings")
        if node.primary_topic and node.primary_topic not in node.topics:
            err(f"primary_topic {node.primary_topic!r} must be listed in topics")
    if node.primary_topic:
        if not isinstance(node.primary_topic, str) or not node.primary_topic.strip():
            err("primary_topic must be a non-empty string")

    return diags
