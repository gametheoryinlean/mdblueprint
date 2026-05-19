"""Generate bounded Markdown-to-Lean linking candidate bundles."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex, index_lean_project
from tools.knowledge.models import Node
from tools.knowledge.renderer import _module_for_declaration


KIND_COMPATIBILITY = {
    "definition": {"def", "structure", "class", "abbrev", "inductive"},
    "concept": {"def", "structure", "class", "abbrev", "inductive"},
    "lemma": {"lemma", "theorem"},
    "proposition": {"lemma", "theorem"},
    "theorem": {"lemma", "theorem"},
    "external-theorem": {"lemma", "theorem"},
}


def _tokens(*values: str) -> set[str]:
    text = " ".join(values).replace("_", " ").replace("-", " ")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return {
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", text.lower())
        if len(token) > 1
    }


def _decl_tokens(decl: LeanDeclaration) -> set[str]:
    return _tokens(decl.qualified_name.replace(".", " "), decl.name)


def _decl_payload(repo_id: str, decl: LeanDeclaration, idx: LeanIndex, *, score: int, reason: str) -> dict[str, Any]:
    return {
        "repository": repo_id,
        "declaration": decl.qualified_name,
        "name": decl.name,
        "module": decl.module or _module_for_declaration(decl, idx),
        "kind": decl.kind,
        "signature": decl.signature,
        "docstring": decl.docstring,
        "namespace": decl.namespace,
        "source_url": decl.source_url,
        "has_sorry": decl.has_sorry,
        "score": score,
        "rank_reason": reason,
    }


def _current_lean(node: Node) -> dict[str, Any] | None:
    if node.lean is None:
        return None
    return {
        "repository": node.lean.repository,
        "modules": list(node.lean.modules),
        "declarations": list(node.lean.declarations),
    }


def _node_payload(node: Node) -> dict[str, Any]:
    statement, _, _proof = node.body.partition("*Proof.*")
    return {
        "id": node.id,
        "title": node.title,
        "kind": node.kind,
        "status": node.status,
        "uses": list(node.uses),
        "tags": list(node.tags),
        "primary_topic": node.primary_topic,
        "topics": list(node.topics),
        "statement": statement.strip(),
        "has_proof": bool(_proof),
        "source_spans": [
            {
                "artifact": span.artifact,
                "locator": span.locator,
                "format": span.format,
                "note": span.note,
            }
            for span in (node.source.spans if node.source else [])
        ],
    }


def build_candidate_bundle(
    node: Node,
    indexes: dict[str, LeanIndex],
    *,
    default_repository: str | None = None,
    max_candidates: int = 5,
    snippet_chars: int = 800,
) -> dict[str, Any]:
    current = _current_lean(node)
    candidates: dict[tuple[str, str], dict[str, Any]] = {}

    if node.lean is not None:
        repo_id = node.lean.repository or default_repository
        if repo_id in indexes:
            idx = indexes[repo_id]
            for decl_name in node.lean.declarations:
                matches = [decl_name] if decl_name in idx.declarations else [
                    q for q in idx.declarations if q.endswith(f".{decl_name}") or q == decl_name
                ]
                for qualified in matches:
                    decl = idx.declarations[qualified]
                    candidates[(repo_id, qualified)] = _decl_payload(
                        repo_id, decl, idx, score=10_000, reason="existing lean frontmatter"
                    )

    node_tokens = _tokens(node.id.replace(".", " "), node.title, " ".join(node.tags))
    compatible = KIND_COMPATIBILITY.get(node.kind, set())

    for repo_id, idx in indexes.items():
        for qualified, decl in idx.declarations.items():
            key = (repo_id, qualified)
            if key in candidates:
                continue
            overlap = node_tokens & _decl_tokens(decl)
            if not overlap:
                continue
            score = len(overlap) * 10
            if decl.kind in compatible:
                score += 5
            if node.primary_topic and node.primary_topic.replace("_", "").lower() in qualified.replace("_", "").lower():
                score += 2
            candidates[key] = _decl_payload(
                repo_id,
                decl,
                idx,
                score=score,
                reason="name/title/topic heuristic",
            )

    ordered = sorted(
        candidates.values(),
        key=lambda c: (-int(c["score"]), str(c["repository"]), str(c["declaration"])),
    )[:max_candidates]
    for candidate in ordered:
        if isinstance(candidate.get("signature"), str) and len(candidate["signature"]) > snippet_chars:
            candidate["signature"] = candidate["signature"][:snippet_chars].rstrip() + "..."

    return {
        "node": _node_payload(node),
        "current_lean": current,
        "candidates": ordered,
        "instructions": {
            "agent_may_choose_none": True,
            "mechanical_link_only": True,
            "do_not_claim_semantic_alignment": True,
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate Lean link candidate bundle for a node.")
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--max-candidates", type=int, default=5)
    args = parser.parse_args(argv)

    ctx = KnowledgeContext.load(args.knowledge_root, lean=False)
    node = ctx.nodes_by_id.get(args.node_id)
    if node is None:
        raise SystemExit(f"node not found: {args.node_id}")
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    bundle = build_candidate_bundle(
        node,
        indexes,
        default_repository=ctx.config.lean.default_repository,
        max_candidates=args.max_candidates,
    )
    print(json.dumps(bundle, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
