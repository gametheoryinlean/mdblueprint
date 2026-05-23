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
