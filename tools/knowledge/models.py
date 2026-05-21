from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceLibraryEntry:
    id: str
    title: str
    short: str | None = None
    authors: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class SourceArtifact:
    id: str
    path: str | None = None


@dataclass(frozen=True)
class SourceSpan:
    locator: str
    artifact: str | None = None
    format: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Source:
    artifacts: list[SourceArtifact] = field(default_factory=list)
    spans: list[SourceSpan] = field(default_factory=list)


@dataclass(frozen=True)
class LeanRef:
    repository: str | None = None
    modules: list[str] = field(default_factory=list)
    declarations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Verification:
    statement: str | None = None
    definition: str | None = None
    proof: str | None = None
    alignment: str | None = None


@dataclass(frozen=True)
class Generality:
    reviewed: bool = False
    prompt: str | None = None
    verdict: str | None = None


VALID_KINDS = frozenset({
    "topic", "concept", "definition", "lemma", "proposition", "theorem",
    "example", "proof-plan", "external-theorem", "task",
})

VALID_STATUSES = frozenset({
    "staged", "needs_statement_review", "needs_definition_review",
    "needs_proof_review", "admitted", "formalized", "proved",
    "blocked", "deprecated",
})

VALID_PLAN_STATUSES = frozenset({
    "candidate", "selected", "rejected", "blocked", "formalized",
})

ADMITTED_STATUSES = frozenset({"admitted", "formalized", "proved"})
STAGED_STATUSES = frozenset({
    "staged", "needs_statement_review", "needs_definition_review",
    "needs_proof_review",
})

MATH_KINDS = frozenset({
    "topic", "concept", "definition", "lemma", "proposition", "theorem",
    "example", "proof-plan", "external-theorem",
})

STATEMENT_KINDS = frozenset({"lemma", "proposition", "theorem", "external-theorem"})
DEFINITION_KINDS = frozenset({"definition", "concept", "topic"})
PROOF_PLAN_TARGET_KINDS = frozenset({"lemma", "proposition", "theorem", "external-theorem"})
GENERALITY_REQUIRED_KINDS = frozenset({
    "topic", "concept", "definition", "lemma", "proposition", "theorem", "external-theorem",
})

FORBIDDEN_HEADINGS = frozenset({
    "status", "implementation notes", "lean interface",
    "task checklist", "agent discussion", "reviewer metadata",
})

VALID_LOCATOR_FORMATS = frozenset({
    "book-page", "section", "arxiv-theorem", "lean-location", "url",
})

VALID_STATEMENT_VALUES = frozenset({"accepted", "needs_revision", "rejected"})
VALID_DEFINITION_VALUES = frozenset({"accepted", "needs_revision", "rejected"})
VALID_PROOF_VALUES = frozenset({"accepted", "gap", "critical", "not_applicable"})
VALID_ALIGNMENT_VALUES = frozenset({"aligned", "pending", "mismatch"})


@dataclass
class Node:
    id: str
    title: str
    kind: str
    status: str
    uses: list[str] = field(default_factory=list)
    target: str | None = None
    plan_status: str | None = None
    lean: LeanRef | None = None
    source: Source | None = None
    verification: Verification | None = None
    generality: Generality | None = None
    tags: list[str] = field(default_factory=list)
    primary_topic: str | None = None
    topics: list[str] = field(default_factory=list)
    body: str = ""
    file_path: Path | None = None
