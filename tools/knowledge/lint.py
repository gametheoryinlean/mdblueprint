"""mdblueprint-lint — orchestrator for deterministic and LLM-backed detectors.

This module owns:
- The Detector protocol shared by every rule (deterministic or LLM-backed).
- The Linter class, which loads nodes, builds the graph, runs detectors, and
  returns a flat list[Diagnostic].
- Text and JSON renderers (added in Task 2).
- The CLI entry point main() (added in Task 3).

Real detectors plug in via the Detector protocol and arrive in PR 3+.
"""
from __future__ import annotations

import argparse
import json as _json
import re
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Protocol

from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.models import ADMITTED_STATUSES, STAGED_STATUSES, Node
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic

LlmRunner = Callable[[str], str]


class Detector(Protocol):
    code: str
    needs_llm: bool

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]: ...


class Linter:
    """Loads a knowledge base and runs a list of detectors against it."""

    def __init__(
        self,
        *,
        detectors: list[Detector],
        llm: LlmRunner | None = None,
    ) -> None:
        self._detectors = detectors
        self._llm = llm

    def run(self, knowledge_root: Path) -> list[Diagnostic]:
        nodes = self._load_nodes(knowledge_root)
        graph, graph_diags = build_graph(nodes)
        out: list[Diagnostic] = list(graph_diags)
        for det in self._detectors:
            if det.needs_llm and self._llm is None:
                continue
            out.extend(det.run(nodes, graph, llm=self._llm))
        return out

    @staticmethod
    def _load_nodes(root: Path) -> list[Node]:
        nodes: list[Node] = []
        for sub in ("nodes", "staged"):
            d = root / sub
            if d.exists():
                nodes.extend(scan_directory(d))
        return nodes


_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_TRAILING_PUNCT_RE = re.compile(r"^[\s\W_]+|[\s\W_]+$", flags=re.UNICODE)


def _normalize(text: str) -> str:
    """Lowercase, collapse internal whitespace, strip leading/trailing punctuation.

    Internal punctuation is preserved so semantically distinct sentences with
    similar surface words still stay apart.
    """
    if text is None:
        return ""
    lowered = text.lower()
    stripped = _LEADING_TRAILING_PUNCT_RE.sub("", lowered)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _ratio(a: str, b: str) -> float:
    """SequenceMatcher ratio over already-normalized strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


_STATEMENT_HEADING_RE = re.compile(r"^##\s+statement\b", flags=re.IGNORECASE | re.MULTILINE)
_HEADING_RE = re.compile(r"^#+\s", flags=re.MULTILINE)


def _statement_text(node: Node) -> str:
    """Return the body text under a `## Statement` section if present, else `""`.

    Used as a secondary similarity signal when titles alone don't trigger.
    """
    body = node.body or ""
    match = _STATEMENT_HEADING_RE.search(body)
    if match is None:
        return ""
    start = match.end()
    # Stop at the next heading of any level.
    next_heading = _HEADING_RE.search(body, pos=start)
    end = next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


@dataclass
class FuzzyTitleDupDetector:
    """Flag admitted node pairs with near-duplicate titles or statements."""

    threshold: float = 0.92
    code: str = "LINT_FUZZY_DUP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        out: list[Diagnostic] = []
        for index, a in enumerate(admitted):
            a_title = _normalize(a.title)
            a_stmt = _normalize(_statement_text(a))
            for b in admitted[index + 1:]:
                b_title = _normalize(b.title)
                score = _ratio(a_title, b_title)
                if score < self.threshold:
                    b_stmt = _normalize(_statement_text(b))
                    if a_stmt and b_stmt:
                        score = max(score, _ratio(a_stmt, b_stmt))
                if score >= self.threshold:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=a.id,
                        message=f"near-duplicate of {b.id!r} (similarity {score:.2f})",
                        file_path=a.file_path,
                        code=self.code,
                        related=(b.id,),
                    ))
        return out


def render_text(diags: list[Diagnostic]) -> str:
    """Render diagnostics as a human-readable, code-grouped text block."""
    if not diags:
        return "✅ No lint findings."
    coded: dict[str, list[Diagnostic]] = {}
    uncoded: list[Diagnostic] = []
    for d in diags:
        if d.code:
            coded.setdefault(d.code, []).append(d)
        else:
            uncoded.append(d)
    lines: list[str] = []
    for code in sorted(coded):
        lines.append(f"── {code} ──")
        for d in coded[code]:
            lines.append(f"  {d}")
    if uncoded:
        lines.append("── (uncoded) ──")
        for d in uncoded:
            lines.append(f"  {d}")
    return "\n".join(lines)


def render_json(diags: list[Diagnostic]) -> str:
    """Render diagnostics as a stable JSON list."""
    payload = [
        {
            "level": d.level,
            "node_id": d.node_id,
            "message": d.message,
            "file_path": str(d.file_path) if d.file_path is not None else None,
            "code": d.code,
            "related": list(d.related),
        }
        for d in diags
    ]
    return _json.dumps(payload, ensure_ascii=False, indent=2)


def _default_detectors() -> list[Detector]:
    """Return the built-in detector list. Empty in PR 2; PR 3+ populates it."""
    return []


def _make_claude_cli_runner(model: str = "claude-sonnet-4-6") -> LlmRunner:
    """Return a runner that calls the `claude` CLI subprocess."""
    def _run(prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--output-format", "text"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    return _run


def _build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="mdblueprint-lint",
        description="Lint a mdblueprint knowledge base for duplicate, structural, "
                    "and reference issues.",
    )
    ap.add_argument("knowledge_root", type=Path,
                    help="Path to the knowledge base root (containing nodes/ and staged/).")
    llm_group = ap.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--llm", action="store_true",
        help="Enable LLM-backed detectors (calls `claude -p`).",
    )
    llm_group.add_argument(
        "--no-llm", action="store_true",
        help="Explicitly disable LLM-backed detectors (default).",
    )
    ap.add_argument("--llm-budget", type=int, default=50,
                    help="Maximum number of LLM calls per run (default: 50). "
                         "Reserved for PR 6+.")
    ap.add_argument("--model", default="claude-sonnet-4-6",
                    help="Claude model to use when --llm is set.")
    ap.add_argument("--cache-dir", type=Path, default=Path(".mdblueprint/lint-cache"),
                    help="Where LLM detectors cache responses. Reserved for PR 6+.")
    ap.add_argument("--no-cache", action="store_true",
                    help="Disable the LLM response cache. Reserved for PR 6+.")
    ap.add_argument("--json", action="store_true",
                    help="Emit findings as JSON instead of grouped text.")
    ap.add_argument("--strict-warnings", action="store_true",
                    help="Exit non-zero when any warning is emitted.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    llm: LlmRunner | None = None
    if args.llm:
        llm = _make_claude_cli_runner(model=args.model)
    linter = Linter(detectors=_default_detectors(), llm=llm)
    diags = linter.run(args.knowledge_root)
    output = render_json(diags) if args.json else render_text(diags)
    print(output)
    if any(d.level == "error" for d in diags):
        return 1
    if args.strict_warnings and any(d.level == "warning" for d in diags):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
