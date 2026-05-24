"""tools.knowledge.lint — public re-export surface.

All symbols that were importable from the old ``tools.knowledge.lint`` module
remain importable from this package unchanged.
"""
from __future__ import annotations

from tools.knowledge.lint._core import (
    Detector,
    Linter,
    LlmRunner,
    _build_arg_parser,
    _default_detectors,
    _make_claude_cli_runner,
    main,
    render_json,
    render_text,
)
from tools.knowledge.lint._detectors import (
    FuzzyTitleDupDetector,
    HierarchyInversionDetector,
    LeanRefKindDetector,
    OrphanDetector,
    PlanPromoteDetector,
    RedundantDepDetector,
    StagedAdmittedOverlapDetector,
    TopicCycleDetector,
    _normalize,
    _ratio,
)
from tools.knowledge.lint._llm import LeanAlignmentLlmDetector, SemanticDupDetector

__all__ = [
    # Core
    "Detector",
    "Linter",
    "LlmRunner",
    "render_text",
    "render_json",
    "main",
    "_make_claude_cli_runner",
    "_build_arg_parser",
    "_default_detectors",
    # Detectors
    "FuzzyTitleDupDetector",
    "StagedAdmittedOverlapDetector",
    "RedundantDepDetector",
    "OrphanDetector",
    "LeanRefKindDetector",
    "PlanPromoteDetector",
    "HierarchyInversionDetector",
    "TopicCycleDetector",
    "SemanticDupDetector",
    "LeanAlignmentLlmDetector",
    # Private helpers re-exported for tests
    "_normalize",
    "_ratio",
]
