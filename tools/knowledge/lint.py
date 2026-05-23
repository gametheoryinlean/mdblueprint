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
import subprocess
import sys
from pathlib import Path
from typing import Callable, Protocol

from tools.knowledge.graph import KnowledgeGraph, build_graph
from tools.knowledge.models import Node
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
