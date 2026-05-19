"""Bounded Markdown-to-Lean semantic alignment reports."""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import re
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_check import check_configured_lean_references
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.models import LeanRef, Node


CLASSIFICATIONS = {
    "aligned",
    "lean_stronger",
    "lean_weaker",
    "lean_special_case",
    "lean_extra_hypotheses",
    "lean_missing_hypotheses",
    "definition_mismatch",
    "uncertain",
}


class LeanAlignmentError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class LeanAlignmentReport:
    node_id: str
    repository: str | None
    declaration: str
    classification: str
    evidence: list[dict[str, str]]
    risks: list[str]
    recommendation: str
    raw: dict[str, Any]


def _indexes(ctx: KnowledgeContext):
    return {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }


def _node_with_decl(node: Node, repository: str | None, declaration: str) -> Node:
    return Node(
        id=node.id,
        title=node.title,
        kind=node.kind,
        status=node.status,
        uses=node.uses,
        lean=LeanRef(repository=repository, modules=[], declarations=[declaration]),
        source=node.source,
        verification=node.verification,
        generality=node.generality,
        tags=node.tags,
        primary_topic=node.primary_topic,
        topics=node.topics,
        body=node.body,
        file_path=node.file_path,
    )


def _resolve_declaration(ctx: KnowledgeContext, node: Node, declaration: str, repository: str | None = None):
    repo_id = repository or (node.lean.repository if node.lean else None) or ctx.config.lean.default_repository
    indexes = _indexes(ctx)
    probe = _node_with_decl(node, repo_id, declaration)
    diags = check_configured_lean_references([probe], ctx.config.lean, indexes)
    problems = [d for d in diags if d.level in {"error", "warning"}]
    if problems:
        raise LeanAlignmentError("; ".join(d.message for d in problems))
    if repo_id is None or repo_id not in indexes:
        raise LeanAlignmentError("Lean repository not configured")
    idx = indexes[repo_id]
    matches = [declaration] if declaration in idx.declarations else [
        q for q in idx.declarations if q.endswith(f".{declaration}") or q == declaration
    ]
    if len(matches) != 1:
        raise LeanAlignmentError(f"Lean declaration not found or ambiguous: {declaration}")
    return repo_id, idx.declarations[matches[0]]


def build_alignment_bundle(knowledge_root: Path, node_id: str, declaration: str) -> dict[str, Any]:
    ctx = KnowledgeContext.load(knowledge_root, lean=False)
    node = ctx.nodes_by_id.get(node_id)
    if node is None:
        raise LeanAlignmentError(f"node not found: {node_id}")
    repo_id, decl = _resolve_declaration(ctx, node, declaration)
    return {
        "node": {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
            "uses": list(node.uses),
            "body": node.body,
            "current_lean": {
                "repository": node.lean.repository if node.lean else None,
                "modules": list(node.lean.modules) if node.lean else [],
                "declarations": list(node.lean.declarations) if node.lean else [],
            },
        },
        "lean_declaration": {
            "repository": repo_id,
            "declaration": decl.qualified_name,
            "kind": decl.kind,
            "module": decl.module,
            "signature": decl.signature,
            "docstring": decl.docstring,
            "source_url": decl.source_url,
            "has_sorry": decl.has_sorry,
        },
        "instructions": {
            "agent_must_not_write_frontmatter": True,
            "return_one_classification": sorted(CLASSIFICATIONS),
            "cite_markdown_and_lean_phrases": True,
        },
    }


def validate_alignment_report(raw: dict[str, Any], knowledge_root: Path) -> LeanAlignmentReport:
    if not isinstance(raw, dict):
        raise LeanAlignmentError("alignment report must be a mapping")
    if raw.get("agent") != "alignment-verifier":
        raise LeanAlignmentError("agent must be 'alignment-verifier'")
    node_id = raw.get("node_id")
    declaration = raw.get("declaration")
    if not isinstance(node_id, str) or not node_id.strip():
        raise LeanAlignmentError("node_id must be a non-empty string")
    if not isinstance(declaration, str) or not declaration.strip():
        raise LeanAlignmentError("declaration must be a non-empty string")
    classification = raw.get("classification")
    if classification not in CLASSIFICATIONS:
        raise LeanAlignmentError("invalid alignment classification")
    evidence = raw.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise LeanAlignmentError("evidence must be a non-empty list")
    parsed_evidence: list[dict[str, str]] = []
    for item in evidence:
        if not isinstance(item, dict):
            raise LeanAlignmentError("evidence entries must be mappings")
        markdown = item.get("markdown")
        lean = item.get("lean")
        note = item.get("note")
        if not all(isinstance(value, str) and value.strip() for value in (markdown, lean, note)):
            raise LeanAlignmentError("evidence entries require markdown, lean, and note strings")
        parsed_evidence.append({"markdown": markdown, "lean": lean, "note": note})
    risks = raw.get("risks") or []
    if not isinstance(risks, list) or not all(isinstance(risk, str) for risk in risks):
        raise LeanAlignmentError("risks must be a list of strings")
    recommendation = raw.get("recommendation")
    if not isinstance(recommendation, str) or not recommendation.strip():
        raise LeanAlignmentError("recommendation must be a non-empty string")

    ctx = KnowledgeContext.load(knowledge_root, lean=False)
    node = ctx.nodes_by_id.get(node_id)
    if node is None:
        raise LeanAlignmentError(f"node not found: {node_id}")
    repository = raw.get("repository")
    if repository is not None and not isinstance(repository, str):
        raise LeanAlignmentError("repository must be a string or null")
    repo_id, decl = _resolve_declaration(ctx, node, declaration, repository)

    return LeanAlignmentReport(
        node_id=node_id,
        repository=repo_id,
        declaration=decl.qualified_name,
        classification=classification,
        evidence=parsed_evidence,
        risks=risks,
        recommendation=recommendation,
        raw=raw,
    )


def write_alignment_report(report: LeanAlignmentReport, reviews_dir: Path) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()
    path = reviews_dir / f"{report.node_id.replace('.', '_')}_lean_alignment_{re.sub(r'[:+]', '_', timestamp)}.md"
    lines = [
        "---",
        "agent: alignment-verifier",
        f"node_id: {report.node_id}",
        f"repository: {report.repository}",
        f"declaration: {report.declaration}",
        f"classification: {report.classification}",
        f'created_at: "{timestamp}"',
        "---",
        "",
        f"# Lean Alignment Review: {report.node_id}",
        "",
        "```yaml",
        yaml.safe_dump(report.raw, sort_keys=False).rstrip(),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build or validate bounded Lean alignment reports.")
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--node-id")
    parser.add_argument("--declaration")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    if args.report:
        raw = yaml.safe_load(args.report.read_text(encoding="utf-8"))
        report = validate_alignment_report(raw, args.knowledge_root)
        path = write_alignment_report(report, args.knowledge_root / "reviews")
        print(f"Wrote Lean alignment report: {path}")
        return
    if not args.node_id or not args.declaration:
        raise SystemExit("--node-id and --declaration are required when not validating --report")
    print(json.dumps(build_alignment_bundle(args.knowledge_root, args.node_id, args.declaration), indent=2))


if __name__ == "__main__":
    main()
