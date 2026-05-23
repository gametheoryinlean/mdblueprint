"""Tests for the lint orchestrator (PR 2 — skeleton only)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.knowledge.lint import Detector, Linter, LlmRunner
from tools.knowledge.validator import Diagnostic


# ── Fake detectors ────────────────────────────────────────────────────────────

@dataclass
class _RecordingDetector:
    code: str = "LINT_FAKE"
    needs_llm: bool = False
    _emit: tuple[Diagnostic, ...] = ()
    last_call: dict = None

    def run(self, nodes, graph, *, llm):
        self.last_call = {"n_nodes": len(nodes), "llm_is_none": llm is None}
        return list(self._emit)


def _emit_one_warning() -> _RecordingDetector:
    return _RecordingDetector(
        code="LINT_FAKE",
        _emit=(Diagnostic("warning", "n.a", "fake", code="LINT_FAKE", related=("n.b",)),),
    )


def _emit_one_info() -> _RecordingDetector:
    return _RecordingDetector(
        code="LINT_INFO",
        _emit=(Diagnostic("info", "n.a", "fyi", code="LINT_INFO"),),
    )


def _make_minimal_knowledge_root(tmp_path: Path) -> Path:
    """Build the smallest valid knowledge root the Linter can load."""
    root = tmp_path / "kb"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Lint Test\n")
    (root / "nodes" / "node_a.md").write_text(
        "---\nid: n.a\ntitle: Node A\nkind: definition\nstatus: admitted\n---\n\n# Node A\n"
    )
    return root


# ── Linter core ───────────────────────────────────────────────────────────────

class TestLinterRun:
    def test_empty_detector_list_returns_no_diagnostics(self, tmp_path):
        root = _make_minimal_knowledge_root(tmp_path)
        linter = Linter(detectors=[])
        diags = linter.run(root)
        # build_graph may emit zero diagnostics for a single-node base; lint
        # itself contributes nothing when no detectors are registered.
        assert all(d.code is None for d in diags)
        assert not any(d.code and d.code.startswith("LINT_") for d in diags)

    def test_detector_is_called_with_nodes_and_graph(self, tmp_path):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _emit_one_warning()
        linter = Linter(detectors=[det])
        linter.run(root)
        assert det.last_call == {"n_nodes": 1, "llm_is_none": True}

    def test_detector_diagnostics_propagate(self, tmp_path):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _emit_one_warning()
        linter = Linter(detectors=[det])
        diags = linter.run(root)
        lint_diags = [d for d in diags if d.code == "LINT_FAKE"]
        assert len(lint_diags) == 1
        assert lint_diags[0].level == "warning"
        assert lint_diags[0].related == ("n.b",)


class TestLinterLlmGating:
    def test_needs_llm_detector_skipped_when_runner_is_none(self, tmp_path):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _RecordingDetector(
            code="LINT_LLM_ONLY",
            needs_llm=True,
            _emit=(Diagnostic("warning", "n.a", "shouldn't run", code="LINT_LLM_ONLY"),),
        )
        linter = Linter(detectors=[det], llm=None)
        diags = linter.run(root)
        assert det.last_call is None  # detector was not invoked
        assert not any(d.code == "LINT_LLM_ONLY" for d in diags)

    def test_needs_llm_detector_runs_when_runner_provided(self, tmp_path):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _RecordingDetector(
            code="LINT_LLM_ONLY",
            needs_llm=True,
            _emit=(Diagnostic("warning", "n.a", "ran", code="LINT_LLM_ONLY"),),
        )
        fake_runner: LlmRunner = lambda prompt: "ok"
        linter = Linter(detectors=[det], llm=fake_runner)
        diags = linter.run(root)
        assert det.last_call == {"n_nodes": 1, "llm_is_none": False}
        assert any(d.code == "LINT_LLM_ONLY" for d in diags)
