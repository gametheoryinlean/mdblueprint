"""Validate and apply Markdown-to-Lean link proposals."""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import re
from pathlib import Path
from typing import Any

import yaml

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.lean_check import check_configured_lean_references
from tools.knowledge.models import LeanRef, Node
from tools.knowledge.parser import parse_file


DECISIONS = {"link", "no_match", "ambiguous", "needs_lean_generation", "needs_human_decision"}


class LeanLinkProposalError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ProposedLean:
    repository: str | None
    modules: list[str]
    declarations: list[str]


@dataclasses.dataclass(frozen=True)
class LeanLinkProposal:
    node_id: str
    decision: str
    proposed_lean: ProposedLean | None
    primary_declaration: str | None
    role_notes: dict[str, str]
    reason: str
    risks: list[str]
    raw: dict[str, Any]


def _as_str_list(raw: Any, field: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise LeanLinkProposalError(f"{field} must be a list of non-empty strings")
    return [item.strip() for item in raw]


def _parse_proposal(raw: dict[str, Any]) -> LeanLinkProposal:
    if not isinstance(raw, dict):
        raise LeanLinkProposalError("proposal must be a mapping")
    if raw.get("agent") != "lean-linking":
        raise LeanLinkProposalError("agent must be 'lean-linking'")
    node_id = raw.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise LeanLinkProposalError("node_id must be a non-empty string")
    decision = raw.get("decision")
    if decision not in DECISIONS:
        raise LeanLinkProposalError(f"decision must be one of {', '.join(sorted(DECISIONS))}")
    if "verification" in raw or "status" in raw:
        raise LeanLinkProposalError("link proposals must not set status or verification/alignment")

    proposed_lean = None
    if decision == "link":
        lean_raw = raw.get("proposed_lean")
        if not isinstance(lean_raw, dict):
            raise LeanLinkProposalError("decision 'link' requires proposed_lean mapping")
        repository = lean_raw.get("repository")
        if repository is not None and (not isinstance(repository, str) or not repository.strip()):
            raise LeanLinkProposalError("proposed_lean.repository must be a non-empty string or null")
        proposed_lean = ProposedLean(
            repository=repository.strip() if isinstance(repository, str) else None,
            modules=_as_str_list(lean_raw.get("modules"), "proposed_lean.modules"),
            declarations=_as_str_list(lean_raw.get("declarations"), "proposed_lean.declarations"),
        )

    primary = raw.get("primary_declaration")
    if primary is not None and not isinstance(primary, str):
        raise LeanLinkProposalError("primary_declaration must be a string or null")
    role_notes_raw = raw.get("role_notes") or {}
    if not isinstance(role_notes_raw, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in role_notes_raw.items()):
        raise LeanLinkProposalError("role_notes must be a mapping of strings")
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise LeanLinkProposalError("reason must be a non-empty string")
    risks = raw.get("risks") or []
    if not isinstance(risks, list) or not all(isinstance(risk, str) for risk in risks):
        raise LeanLinkProposalError("risks must be a list of strings")

    return LeanLinkProposal(
        node_id=node_id.strip(),
        decision=decision,
        proposed_lean=proposed_lean,
        primary_declaration=primary,
        role_notes=dict(role_notes_raw),
        reason=reason.strip(),
        risks=risks,
        raw=raw,
    )


def _proposal_node(proposal: LeanLinkProposal, ctx: KnowledgeContext) -> Node:
    node = ctx.nodes_by_id.get(proposal.node_id)
    if node is None:
        raise LeanLinkProposalError(f"node not found: {proposal.node_id}")
    if proposal.proposed_lean is None:
        return node
    return Node(
        id=node.id,
        title=node.title,
        kind=node.kind,
        status=node.status,
        uses=node.uses,
        target=node.target,
        plan_status=node.plan_status,
        lean=LeanRef(
            repository=proposal.proposed_lean.repository,
            modules=proposal.proposed_lean.modules,
            declarations=proposal.proposed_lean.declarations,
        ),
        source=node.source,
        verification=node.verification,
        generality=node.generality,
        tags=node.tags,
        primary_topic=node.primary_topic,
        topics=node.topics,
        body=node.body,
        file_path=node.file_path,
    )


def validate_lean_link_proposal(raw: dict[str, Any], knowledge_root: Path) -> LeanLinkProposal:
    proposal = _parse_proposal(raw)
    ctx = KnowledgeContext.load(knowledge_root, lean=False)
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    node = _proposal_node(proposal, ctx)
    if proposal.proposed_lean is not None:
        diags = check_configured_lean_references(
            [node],
            ctx.config.lean,
            indexes,
            strict_placeholders=False,
        )
        errors_or_warnings = [d for d in diags if d.level in {"error", "warning"}]
        if errors_or_warnings:
            raise LeanLinkProposalError("; ".join(d.message for d in errors_or_warnings))
    return proposal


def _timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def write_link_proposal_report(proposal: LeanLinkProposal, reviews_dir: Path) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    safe_ts = re.sub(r"[:+]", "_", timestamp)
    path = reviews_dir / f"{proposal.node_id.replace('.', '_')}_lean_linking_{safe_ts}.md"
    lines = [
        "---",
        "agent: lean-linking",
        f"node_id: {proposal.node_id}",
        f"decision: {proposal.decision}",
        f'created_at: "{timestamp}"',
        "---",
        "",
        f"# Lean Link Proposal: {proposal.node_id}",
        "",
        "```yaml",
        yaml.safe_dump(proposal.raw, sort_keys=False).rstrip(),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise LeanLinkProposalError("node file has no YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise LeanLinkProposalError("node file has malformed YAML frontmatter")
    fm = yaml.safe_load(text[4:end]) or {}
    if not isinstance(fm, dict):
        raise LeanLinkProposalError("node frontmatter is not a mapping")
    return fm, text[end + len("\n---\n"):]


def _lean_yaml(proposal: LeanLinkProposal) -> dict[str, Any]:
    if proposal.proposed_lean is None:
        raise LeanLinkProposalError("proposal does not contain proposed_lean")
    lean: dict[str, Any] = {
        "modules": proposal.proposed_lean.modules,
        "declarations": proposal.proposed_lean.declarations,
    }
    if proposal.proposed_lean.repository is not None:
        lean = {"repository": proposal.proposed_lean.repository, **lean}
    return lean


def apply_lean_link_proposal(proposal: LeanLinkProposal, knowledge_root: Path) -> Path:
    if proposal.decision != "link" or proposal.proposed_lean is None:
        raise LeanLinkProposalError("only decision 'link' can be applied")
    ctx = KnowledgeContext.load(knowledge_root, lean=False)
    node = ctx.nodes_by_id.get(proposal.node_id)
    if node is None or node.file_path is None:
        raise LeanLinkProposalError(f"node not found: {proposal.node_id}")

    # Re-parse from disk immediately before writing so unrelated fields are preserved.
    parse_file(node.file_path)
    text = node.file_path.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    fm["lean"] = _lean_yaml(proposal)
    rendered = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    node.file_path.write_text(f"---\n{rendered}\n---\n{body}", encoding="utf-8")
    return node.file_path


def _load_proposal(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LeanLinkProposalError("proposal file must contain a mapping")
    return raw


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate and record Markdown-to-Lean link proposals.")
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply validated lean frontmatter")
    args = parser.parse_args(argv)

    try:
        proposal = validate_lean_link_proposal(_load_proposal(args.proposal), args.knowledge_root)
        report = write_link_proposal_report(proposal, args.knowledge_root / "reviews")
        if args.apply:
            path = apply_lean_link_proposal(proposal, args.knowledge_root)
            print(f"Applied Lean link proposal to {path}")
        else:
            print(f"Wrote Lean link proposal report: {report}")
    except LeanLinkProposalError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
