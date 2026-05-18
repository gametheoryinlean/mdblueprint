"""Deterministic staged-to-nodes admission pipeline."""
from __future__ import annotations

import argparse
import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path

from tools.knowledge.admit import (
    _find_reviews,
    admission_evidence_diagnostics,
)
from tools.knowledge.export import home_topic_for_node, topic_path
from tools.knowledge.graph import build_graph
from tools.knowledge.models import GENERALITY_REQUIRED_KINDS, Node
from tools.knowledge.parser import parse_file, scan_directory
from tools.knowledge.validator import Diagnostic, validate_node


@dataclass
class PipelineGate:
    name: str
    status: str
    messages: list[str]


@dataclass
class PipelineResult:
    success: bool
    node_id: str
    gates: list[PipelineGate]
    target_path: Path | None = None
    report_path: Path | None = None

    def to_json_dict(self) -> dict:
        return {
            "success": self.success,
            "node_id": self.node_id,
            "target_path": str(self.target_path) if self.target_path is not None else None,
            "report_path": str(self.report_path) if self.report_path is not None else None,
            "gates": [
                {
                    "name": gate.name,
                    "status": gate.status,
                    "messages": gate.messages,
                }
                for gate in self.gates
            ],
        }


def _gate(name: str, diags: list[Diagnostic]) -> PipelineGate:
    errors = [d for d in diags if d.level == "error"]
    status = "failed" if errors else "passed"
    return PipelineGate(name=name, status=status, messages=[d.message for d in errors])


def _generality_diagnostics(node: Node) -> list[Diagnostic]:
    if node.kind in GENERALITY_REQUIRED_KINDS:
        if node.generality is None or not node.generality.reviewed:
            return [Diagnostic("error", node.id, "generality gate not completed", node.file_path)]
    return []


def _review_diagnostics(node: Node, knowledge_root: Path, require_reviews: bool) -> list[Diagnostic]:
    if not require_reviews:
        return []
    reviews = _find_reviews(knowledge_root / "reviews", node.id)
    if reviews:
        return []
    return [Diagnostic("error", node.id, "no review reports found", node.file_path)]


def _candidate_as_admitted(node: Node) -> Node:
    return Node(
        id=node.id,
        title=node.title,
        kind=node.kind,
        status="admitted",
        uses=node.uses,
        target=node.target,
        plan_status=node.plan_status,
        lean=node.lean,
        source=node.source,
        verification=node.verification,
        generality=node.generality,
        tags=node.tags,
        primary_topic=node.primary_topic,
        topics=node.topics,
        body=node.body,
        file_path=node.file_path,
    )


def _dag_diagnostics(node: Node, knowledge_root: Path) -> list[Diagnostic]:
    nodes_dir = knowledge_root / "nodes"
    existing = scan_directory(nodes_dir) if nodes_dir.exists() else []
    _, graph_diags = build_graph(existing + [_candidate_as_admitted(node)])
    return [d for d in graph_diags if d.level == "error" and d.node_id == node.id]


def _write_admitted_node(staged_path: Path, knowledge_root: Path, node: Node) -> Path:
    nodes_dir = knowledge_root / "nodes"
    target_dir = nodes_dir / topic_path(home_topic_for_node(node))
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / staged_path.name
    text = staged_path.read_text(encoding="utf-8")
    text = re.sub(
        r"^status:\s*\S+",
        "status: admitted",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    target_path.write_text(text, encoding="utf-8")
    staged_path.unlink()
    return target_path


def _write_block_report(node: Node, knowledge_root: Path, gate: PipelineGate) -> Path:
    reviews_dir = knowledge_root / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    slug = node.id.replace(".", "_")
    timestamp = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
    safe_ts = re.sub(r"[:+]", "_", timestamp)
    path = reviews_dir / f"{slug}_admission_blocked_{safe_ts}.md"
    lines = [
        "---",
        "agent: admission-pipeline",
        "decision: blocked",
        f"blocked_gate: {gate.name}",
        "target:",
        f"  node_id: {node.id}",
        f'created_at: "{timestamp}"',
        "---",
        "",
        f"# Admission Blocked: {node.id}",
        "",
        f"Blocked gate: `{gate.name}`",
        "",
        "## Required Action",
        "",
    ]
    lines.extend(f"- {message}" for message in gate.messages)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def run_admission_pipeline(
    staged_path: Path,
    knowledge_root: Path,
    *,
    require_reviews: bool = True,
    dry_run: bool = False,
) -> PipelineResult:
    node = parse_file(staged_path)
    gates: list[PipelineGate] = []

    gate_checks = [
        ("schema", validate_node(node, is_staged_dir=True)),
        ("generality", _generality_diagnostics(node)),
        ("verification", admission_evidence_diagnostics(node)),
        ("reviews", _review_diagnostics(node, knowledge_root, require_reviews)),
        ("dag", _dag_diagnostics(node, knowledge_root)),
    ]

    for name, diags in gate_checks:
        gate = _gate(name, diags)
        gates.append(gate)
        if gate.status == "failed":
            report_path = _write_block_report(node, knowledge_root, gate)
            return PipelineResult(False, node.id, gates, report_path=report_path)

    if dry_run:
        gates.append(PipelineGate("write", "skipped", ["dry run"]))
        return PipelineResult(True, node.id, gates)

    target_path = _write_admitted_node(staged_path, knowledge_root, node)
    gates.append(PipelineGate("write", "passed", []))
    return PipelineResult(True, node.id, gates, target_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run staged-to-nodes admission gates.")
    parser.add_argument("staged_path", type=Path)
    parser.add_argument("knowledge_root", type=Path, nargs="?", default=Path("docs/knowledge"))
    parser.add_argument("--no-reviews", action="store_true", help="Do not require review reports")
    parser.add_argument("--dry-run", action="store_true", help="Run gates without moving the node")
    args = parser.parse_args(argv)

    result = run_admission_pipeline(
        args.staged_path,
        args.knowledge_root,
        require_reviews=not args.no_reviews,
        dry_run=args.dry_run,
    )
    print(json.dumps(result.to_json_dict(), indent=2, sort_keys=True))
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
