"""Lint orchestrator: Detector protocol, Linter, renderers, CLI, and main."""
from __future__ import annotations

import argparse
import json as _json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

from tools.knowledge.graph import build_graph
from tools.knowledge.models import Node
from tools.knowledge.parser import scan_directory
from tools.knowledge.validator import Diagnostic

if TYPE_CHECKING:
    from tools.knowledge.config import LintConfig
    from tools.knowledge.lean_index import LeanIndex
    from tools.knowledge.lint._cache import _BudgetTracker, _LintCache

LlmRunner = Callable[[str], str]


class Detector(Protocol):
    code: str
    needs_llm: bool

    def run(
        self,
        nodes: list[Node],
        graph,
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


def _default_detectors(
    config: "LintConfig | None" = None,
    *,
    lean_indexes: "dict[str, LeanIndex] | None" = None,
    cache: "_LintCache | None" = None,
    budget: "_BudgetTracker | None" = None,
) -> list[Detector]:
    """Return the built-in detector list."""
    from tools.knowledge.config import LintConfig as _LintConfig
    from tools.knowledge.lint._cache import (
        _BudgetTracker as _BT,
        _LintCache as _LC,
    )
    from tools.knowledge.lint._detectors import (
        FuzzyTitleDupDetector,
        HierarchyInversionDetector,
        LeanModuleFragmentedDetector,
        LeanRefKindDetector,
        OrphanDetector,
        PlanPromoteDetector,
        ProseDepConsistencyDetector,
        RedundantDepDetector,
        StagedAdmittedOverlapDetector,
        TopicCycleDetector,
        TopicLeanAlignmentDetector,
    )
    from tools.knowledge.lint._llm import (
        LeanAlignmentLlmDetector,
        SemanticDupDetector,
    )

    cfg = config if config is not None else _LintConfig()
    cache = cache if cache is not None else _LC(cache_dir=None)
    budget = budget if budget is not None else _BT(budget=None)
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
        LeanModuleFragmentedDetector(),
        LeanRefKindDetector(indexes=lean_indexes),
        PlanPromoteDetector(severity=cfg.plan_promote_severity),
        ProseDepConsistencyDetector(),
        HierarchyInversionDetector(severity=cfg.hierarchy_inversion_severity),
        TopicCycleDetector(),
        TopicLeanAlignmentDetector(),
        SemanticDupDetector(
            cache=cache,
            budget=budget,
            candidate_threshold=cfg.semantic_candidate_threshold,
        ),
        LeanAlignmentLlmDetector(
            cache=cache,
            budget=budget,
            indexes=lean_indexes,
        ),
    ]


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
    from tools.knowledge.config import load_project_config
    from tools.knowledge.lean_index import index_lean_project
    from tools.knowledge.lint._cache import _BudgetTracker, _LintCache
    import tools.knowledge.lint as _lint_pkg

    config = load_project_config(args.knowledge_root)

    lean_indexes: dict[str, "LeanIndex"] = {}
    for repo_id, repo in config.lean.repositories.items():
        if not repo.local_path.exists():
            continue
        try:
            lean_indexes[repo_id] = index_lean_project(repo.local_path, repository=repo)
        except Exception:
            # Indexing failures are not lint errors — they belong to
            # `mdblueprint-check`. Skip the repo silently here; the
            # LeanRefKindDetector falls back to "no index" behavior
            # when none of the configured repos resolved.
            continue
    if (
        config.lean.default_repository
        and config.lean.default_repository in lean_indexes
    ):
        # Alias the chosen default under the literal "default" key so the
        # detector's lookup `indexes.get("default") or next(...)` finds it
        # for nodes whose lean.repository is unset.
        lean_indexes.setdefault(
            "default", lean_indexes[config.lean.default_repository]
        )

    cache_dir = None if args.no_cache else args.cache_dir
    cache = _LintCache(cache_dir=cache_dir)
    budget = _BudgetTracker(budget=args.llm_budget)

    llm: LlmRunner | None = None
    if args.llm:
        llm = _make_claude_cli_runner(model=args.model)
    linter = Linter(
        detectors=_lint_pkg._default_detectors(
            config.lint,
            lean_indexes=lean_indexes or None,
            cache=cache,
            budget=budget,
        ),
        llm=llm,
    )
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
