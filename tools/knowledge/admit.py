"""Staged-to-admitted workflow: validate and move nodes into the knowledge base."""
from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.knowledge.graph import build_graph
from tools.knowledge.models import (
    ADMITTED_STATUSES,
    GENERALITY_REQUIRED_KINDS,
    Node,
)
from tools.knowledge.parser import parse_file, scan_directory
from tools.knowledge.validator import Diagnostic, validate_node


@dataclass
class AdmissionResult:
    success: bool
    node_id: str
    diagnostics: list[Diagnostic]
    target_path: Path | None = None


def _find_reviews(reviews_dir: Path, node_id: str) -> list[Path]:
    if not reviews_dir.exists():
        return []
    return sorted(p for p in reviews_dir.rglob("*.md") if node_id in p.read_text(encoding="utf-8"))


def admit_node(
    staged_path: Path,
    knowledge_root: Path,
    *,
    require_reviews: bool = True,
) -> AdmissionResult:
    diags: list[Diagnostic] = []
    node = parse_file(staged_path)
    nid = node.id

    # Validate as staged first
    staged_diags = validate_node(node, is_staged_dir=True)
    errors = [d for d in staged_diags if d.level == "error"]
    if errors:
        return AdmissionResult(False, nid, errors)

    # Check generality gate for required kinds
    if node.kind in GENERALITY_REQUIRED_KINDS:
        if node.generality is None or not node.generality.reviewed:
            diags.append(Diagnostic("error", nid, "generality gate not completed", node.file_path))

    # Check review reports exist
    reviews_dir = knowledge_root / "reviews"
    if require_reviews:
        reviews = _find_reviews(reviews_dir, nid)
        if not reviews:
            diags.append(Diagnostic("error", nid, "no review reports found", node.file_path))

    # Build graph with all existing nodes + this candidate to check DAG
    nodes_dir = knowledge_root / "nodes"
    existing = scan_directory(nodes_dir) if nodes_dir.exists() else []
    candidate = Node(
        id=node.id,
        title=node.title,
        kind=node.kind,
        status="admitted",
        uses=node.uses,
        lean=node.lean,
        source=node.source,
        verification=node.verification,
        generality=node.generality,
        tags=node.tags,
        body=node.body,
        file_path=node.file_path,
    )
    _, graph_diags = build_graph(existing + [candidate])
    graph_errors = [d for d in graph_diags if d.level == "error" and d.node_id == nid]
    diags.extend(graph_errors)

    if any(d.level == "error" for d in diags):
        return AdmissionResult(False, nid, diags)

    # Determine target path
    parts = nid.split(".")
    topic = parts[0] if len(parts) > 1 else "misc"
    target_dir = nodes_dir / topic
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / staged_path.name

    # Update status in the file content
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

    return AdmissionResult(True, nid, diags, target_path)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m tools.knowledge.admit <staged_node_path> [knowledge_root]")
        sys.exit(1)

    staged_path = Path(sys.argv[1])
    knowledge_root = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/knowledge")

    result = admit_node(staged_path, knowledge_root)

    for d in result.diagnostics:
        print(d)

    if result.success:
        print(f"\nAdmitted {result.node_id} -> {result.target_path}")
    else:
        print(f"\nAdmission blocked for {result.node_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
