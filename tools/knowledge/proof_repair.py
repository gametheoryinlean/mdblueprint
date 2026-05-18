"""Source-first proof repair orchestration."""
from __future__ import annotations

import dataclasses
import datetime
import re
from collections.abc import Callable
from pathlib import Path

from tools.knowledge.models import Node, STATEMENT_KINDS
from tools.knowledge.parser import scan_directory
from tools.knowledge.proof_fill import (
    CodexRunner,
    ProofFillReport,
    run_proof_fill,
    write_failure_report,
)


SourceRecoverer = Callable[[Node, dict[str, Node]], "SourceRecoveryResult"]


@dataclasses.dataclass
class SourceRecoveryResult:
    decision: str
    proof: str | None = None
    hint: str | None = None
    reason: str = ""
    used_node_ids: list[str] = dataclasses.field(default_factory=list)
    missing_dependencies: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ProofRepairResult:
    outcome: str
    node_id: str
    source_report_path: Path | None = None
    proof_fill_report_path: Path | None = None
    request_paths: list[Path] = dataclasses.field(default_factory=list)
    proof_fill_report: ProofFillReport | None = None


def _has_proof(node: Node) -> bool:
    return "*Proof.*" in node.body or "**Proof.**" in node.body


def _proof_accepted(node: Node) -> bool:
    return node.verification is not None and node.verification.proof == "accepted"


def _has_source_spans(node: Node) -> bool:
    return node.source is not None and bool(node.source.spans)


def find_proof_recovery_candidates(knowledge_root: Path) -> list[Node]:
    nodes: list[Node] = []
    for subdir in ("nodes", "staged"):
        root = knowledge_root / subdir
        if root.exists():
            nodes.extend(scan_directory(root))
    return [
        node
        for node in nodes
        if node.kind in STATEMENT_KINDS
        and not _has_proof(node)
        and not _proof_accepted(node)
        and _has_source_spans(node)
    ]


def _timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def _safe_timestamp(timestamp: str) -> str:
    return re.sub(r"[:+]", "_", timestamp)


def write_source_recovery_report(
    node: Node,
    result: SourceRecoveryResult,
    reviews_dir: Path,
) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    path = reviews_dir / f"{node.id.replace('.', '_')}_source_proof_recovery_{_safe_timestamp(timestamp)}.md"
    lines = [
        "---",
        "agent: source-proof-recovery",
        f"decision: {result.decision}",
        "target:",
        f"  node_id: {node.id}",
        f'created_at: "{timestamp}"',
        "---",
        "",
        f"# Source Proof Recovery: {node.id}",
        "",
        f"**Decision:** {result.decision}",
        "",
        "## Reason",
        "",
        result.reason or "",
        "",
    ]
    if result.hint:
        lines += ["## Source Hint", "", result.hint, ""]
    if result.proof:
        lines += ["## Recovered Proof", "", result.proof, ""]
    if result.used_node_ids:
        lines += ["## Used Node IDs", ""]
        lines.extend(f"- {node_id}" for node_id in result.used_node_ids)
        lines.append("")
    if result.missing_dependencies:
        lines += ["## Missing Dependencies", ""]
        lines.extend(f"- {dep}" for dep in result.missing_dependencies)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _insert_source_proof(node: Node, proof_text: str) -> None:
    if node.file_path is None or _has_proof(node):
        return
    text = node.file_path.read_text(encoding="utf-8")
    node.file_path.write_text(text.rstrip("\n") + f"\n\n*Proof.* {proof_text.strip()}\n", encoding="utf-8")


def _write_missing_dependency_requests(
    node: Node,
    missing_dependencies: list[str],
    requests_dir: Path,
) -> list[Path]:
    requests_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    timestamp = _timestamp()
    for index, description in enumerate(missing_dependencies, start=1):
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", description).strip("_").lower() or "missing_dependency"
        path = requests_dir / f"{node.id.replace('.', '_')}_{slug}_{index}.md"
        path.write_text(
            "\n".join([
                "---",
                f"request_id: {node.id.replace('.', '-')}-proof-dependency-{index}",
                "kind: missing-dependency",
                "requested_by: source-proof-recovery",
                "target:",
                f"  node_id: {node.id}",
                f'created_at: "{timestamp}"',
                "---",
                "",
                f"# Missing Proof Dependency for {node.id}",
                "",
                description,
                "",
            ]),
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def run_proof_repair(
    node: Node,
    all_nodes: dict[str, Node],
    *,
    knowledge_root: Path,
    source_recoverer: SourceRecoverer,
    generator: CodexRunner,
    verifier: CodexRunner,
    max_rounds: int = 2,
) -> ProofRepairResult:
    reviews_dir = knowledge_root / "reviews"
    requests_dir = knowledge_root / "requests"
    source_report_path: Path | None = None
    request_paths: list[Path] = []
    source_hint: str | None = None

    if _has_source_spans(node):
        source_result = source_recoverer(node, all_nodes)
        source_report_path = write_source_recovery_report(node, source_result, reviews_dir)
        request_paths = _write_missing_dependency_requests(node, source_result.missing_dependencies, requests_dir)

        if source_result.decision in {"recovered", "partial"} and source_result.proof:
            _insert_source_proof(node, source_result.proof)
            return ProofRepairResult(
                outcome="source_recovered",
                node_id=node.id,
                source_report_path=source_report_path,
                request_paths=request_paths,
            )
        if source_result.decision == "hint_only" and source_result.hint:
            source_hint = source_result.hint

    proof_fill_report = run_proof_fill(
        node,
        all_nodes,
        generator=generator,
        verifier=verifier,
        max_rounds=max_rounds,
        source_hint=source_hint,
    )
    if proof_fill_report.outcome == "accepted":
        return ProofRepairResult(
            outcome="proof_fill_accepted",
            node_id=node.id,
            source_report_path=source_report_path,
            request_paths=request_paths,
            proof_fill_report=proof_fill_report,
        )

    proof_fill_report_path = write_failure_report(proof_fill_report, reviews_dir)
    return ProofRepairResult(
        outcome="blocked",
        node_id=node.id,
        source_report_path=source_report_path,
        proof_fill_report_path=proof_fill_report_path,
        request_paths=request_paths,
        proof_fill_report=proof_fill_report,
    )
