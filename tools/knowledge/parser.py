"""Parse Markdown knowledge nodes from files."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from tools.knowledge.models import (
    Generality,
    LeanRef,
    Node,
    Source,
    SourceArtifact,
    SourceSpan,
    Verification,
)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)", re.DOTALL)


def _parse_source(raw: dict | None) -> Source | None:
    if raw is None:
        return None
    artifacts = []
    for a in raw.get("artifacts") or []:
        if isinstance(a, dict):
            artifacts.append(SourceArtifact(id=a["id"], path=a["path"]))
        else:
            artifacts.append(SourceArtifact(id=str(a), path=str(a)))
    spans = []
    for s in raw.get("spans") or []:
        spans.append(SourceSpan(
            locator=s.get("locator", ""),
            artifact=s.get("artifact"),
            format=s.get("format"),
            note=s.get("note"),
        ))
    return Source(artifacts=artifacts, spans=spans)


def _parse_lean(raw: dict | None) -> LeanRef | None:
    if raw is None:
        return None
    return LeanRef(
        repository=raw.get("repository"),
        modules=raw.get("modules") or [],
        declarations=raw.get("declarations") or [],
    )


def _parse_verification(raw: dict | None) -> Verification | None:
    if raw is None:
        return None
    return Verification(
        statement=raw.get("statement"),
        definition=raw.get("definition"),
        proof=raw.get("proof"),
        alignment=raw.get("alignment"),
    )


def _parse_generality(raw: dict | None) -> Generality | None:
    if raw is None:
        return None
    return Generality(
        reviewed=bool(raw.get("reviewed", False)),
        prompt=raw.get("prompt"),
        verdict=raw.get("verdict"),
    )


def parse_node(text: str, file_path: Path | None = None) -> Node:
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        raise ValueError(f"No YAML frontmatter found in {file_path or '<string>'}")
    fm_text, body = m.group(1), m.group(2)
    fm = yaml.safe_load(fm_text)
    if not isinstance(fm, dict):
        raise ValueError(f"Frontmatter is not a mapping in {file_path or '<string>'}")
    return Node(
        id=fm.get("id", ""),
        title=fm.get("title", ""),
        kind=fm.get("kind", ""),
        status=fm.get("status", ""),
        uses=fm.get("uses") or [],
        target=fm.get("target"),
        plan_status=fm.get("plan_status"),
        lean=_parse_lean(fm.get("lean")),
        source=_parse_source(fm.get("source")),
        verification=_parse_verification(fm.get("verification")),
        generality=_parse_generality(fm.get("generality")),
        tags=fm.get("tags") or [],
        primary_topic=fm.get("primary_topic") or None,
        topics=fm.get("topics") or [],
        body=body.strip(),
        file_path=file_path,
    )


def parse_file(path: Path) -> Node:
    return parse_node(path.read_text(encoding="utf-8"), file_path=path)


def parse_node_id(node_id: str) -> tuple[str, str]:
    """Split a node id into (topic_prefix, local_name)."""
    if "." in node_id:
        parts = node_id.split(".", 1)
        return parts[0], parts[1]
    return node_id, ""


def scan_directory(root: Path) -> list[Node]:
    nodes = []
    for p in sorted(root.rglob("*.md")):
        if p.name == "topics.md":
            continue
        nodes.append(parse_file(p))
    return nodes
