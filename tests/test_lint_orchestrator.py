"""Tests for the lint orchestrator (PR 2 — skeleton only)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from tools.knowledge.lint import (
    Detector,
    Linter,
    LlmRunner,
    _make_claude_cli_runner,
    main,
    render_json,
    render_text,
)
from tools.knowledge.validator import Diagnostic


# ── Fake detectors ────────────────────────────────────────────────────────────

@dataclass
class _RecordingDetector:
    code: str = "LINT_FAKE"
    needs_llm: bool = False
    _emit: tuple[Diagnostic, ...] = ()
    last_call: dict | None = None

    def run(self, nodes, graph, *, llm):
        self.last_call = {"n_nodes": len(nodes), "llm_is_none": llm is None}
        return list(self._emit)


def _emit_one_warning() -> _RecordingDetector:
    return _RecordingDetector(
        code="LINT_FAKE",
        _emit=(Diagnostic("warning", "n.a", "fake", code="LINT_FAKE", related=("n.b",)),),
    )


def _make_minimal_knowledge_root(tmp_path: Path) -> Path:
    """Build the smallest valid knowledge root the Linter can load.

    Two connected nodes so PR 4's OrphanDetector stays quiet at defaults:
    n.b uses n.a, giving n.a an in-edge and n.b an out-edge.
    """
    root = tmp_path / "kb"
    (root / "nodes").mkdir(parents=True)
    (root / "staged").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Lint Test\n")
    (root / "nodes" / "node_a.md").write_text(
        "---\nid: n.a\ntitle: Node A\nkind: definition\nstatus: admitted\n---\n\n# Node A\n"
    )
    (root / "nodes" / "node_b.md").write_text(
        "---\nid: n.b\ntitle: Node B\nkind: definition\nstatus: admitted\n"
        "uses:\n  - n.a\n---\n\n# Node B\n"
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
        assert det.last_call == {"n_nodes": 2, "llm_is_none": True}

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
        assert det.last_call == {"n_nodes": 2, "llm_is_none": False}
        assert any(d.code == "LINT_LLM_ONLY" for d in diags)


# ── Renderers ─────────────────────────────────────────────────────────────────

class TestRenderText:
    def test_no_findings_renders_clean_message(self):
        out = render_text([])
        assert "No lint findings" in out

    def test_findings_grouped_by_code(self):
        diags = [
            Diagnostic("warning", "n.a", "first", code="LINT_A"),
            Diagnostic("warning", "n.b", "second", code="LINT_A"),
            Diagnostic("info", "n.c", "third", code="LINT_B"),
        ]
        out = render_text(diags)
        # Each rule code appears once as a group header, in stable (sorted) order.
        assert out.index("LINT_A") < out.index("LINT_B")
        # Each finding's node id and message appear under its group.
        assert "n.a" in out and "first" in out
        assert "n.b" in out and "second" in out
        assert "n.c" in out and "third" in out

    def test_diagnostics_without_code_render_under_uncoded_group(self):
        diags = [Diagnostic("warning", "n.x", "raw")]
        out = render_text(diags)
        assert "n.x" in out and "raw" in out


class TestRenderJson:
    def test_empty_renders_empty_list(self):
        assert json.loads(render_json([])) == []

    def test_findings_serialize_all_fields(self, tmp_path):
        diags = [
            Diagnostic(
                "warning", "n.a", "dup",
                file_path=tmp_path / "n_a.md",
                code="LINT_FUZZY_DUP",
                related=("n.b",),
            ),
        ]
        parsed = json.loads(render_json(diags))
        assert isinstance(parsed, list) and len(parsed) == 1
        item = parsed[0]
        assert item["level"] == "warning"
        assert item["node_id"] == "n.a"
        assert item["message"] == "dup"
        assert item["code"] == "LINT_FUZZY_DUP"
        assert item["related"] == ["n.b"]
        assert item["file_path"].endswith("n_a.md")

    def test_none_file_path_serializes_as_null(self):
        parsed = json.loads(render_json([Diagnostic("info", "n.x", "m")]))
        assert parsed[0]["file_path"] is None


# ── CLI ───────────────────────────────────────────────────────────────────────

class TestCli:
    def test_smoke_no_detectors_exits_zero_with_no_findings(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _make_minimal_knowledge_root(tmp_path)
        # The default detectors (FuzzyTitleDup + StagedAdmittedOverlap) need at
        # least two nodes to surface anything; the single-node minimal kb is quiet.
        rc = main([str(root)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "No lint findings" in out

    def test_strict_warnings_promotes_warning_to_exit_one(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _make_minimal_knowledge_root(tmp_path)
        # Inject a default-detector list with one warning emitter for this test.
        det = _emit_one_warning()
        monkeypatch.setattr(
            "tools.knowledge.lint._default_detectors", lambda *_a, **_kw: [det]
        )
        rc = main([str(root), "--strict-warnings"])
        out = capsys.readouterr().out
        assert rc == 1
        assert "LINT_FAKE" in out

    def test_warning_without_strict_still_exits_zero(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _emit_one_warning()
        monkeypatch.setattr(
            "tools.knowledge.lint._default_detectors", lambda *_a, **_kw: [det]
        )
        rc = main([str(root)])
        assert rc == 0

    def test_json_output_parses(self, tmp_path, capsys, monkeypatch):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _emit_one_warning()
        monkeypatch.setattr(
            "tools.knowledge.lint._default_detectors", lambda *_a, **_kw: [det]
        )
        main([str(root), "--json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert any(item["code"] == "LINT_FAKE" for item in parsed)

    def test_no_llm_is_the_default_and_skips_llm_detectors(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _RecordingDetector(
            code="LINT_LLM_ONLY",
            needs_llm=True,
            _emit=(Diagnostic("warning", "n.a", "should be skipped", code="LINT_LLM_ONLY"),),
        )
        monkeypatch.setattr(
            "tools.knowledge.lint._default_detectors", lambda *_a, **_kw: [det]
        )
        rc = main([str(root)])
        assert rc == 0
        assert det.last_call is None

    def test_error_level_diagnostic_exits_nonzero(
        self, tmp_path, capsys
    ):
        """build_graph errors (e.g., missing dependency) must fail the lint run."""
        root = tmp_path / "kb"
        (root / "nodes").mkdir(parents=True)
        (root / "staged").mkdir(parents=True)
        (root / "mdblueprint.yml").write_text("site:\n  title: Lint Test\n")
        # Node A claims to use n.missing, which doesn't exist anywhere.
        # status=admitted means build_graph emits "error" (not "warning") for the missing dep.
        (root / "nodes" / "node_a.md").write_text(
            "---\nid: n.a\ntitle: Node A\nkind: definition\nstatus: admitted\n"
            "uses: [n.missing]\n---\n\n# Node A\n"
        )
        rc = main([str(root)])
        out = capsys.readouterr().out
        assert rc == 1
        # The error message from build_graph should appear in the output.
        assert "n.missing" in out

    def test_llm_and_no_llm_are_mutually_exclusive(self, tmp_path):
        """argparse must reject --llm and --no-llm together."""
        root = _make_minimal_knowledge_root(tmp_path)
        with pytest.raises(SystemExit):
            main([str(root), "--llm", "--no-llm"])


class TestClaudeRunnerFactory:
    def test_factory_returns_callable_without_calling_subprocess(self):
        runner = _make_claude_cli_runner(model="claude-sonnet-4-6")
        assert callable(runner)
        # Calling runner() would actually invoke `claude`; we only verify shape.


class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            StagedAdmittedOverlapDetector,
            _default_detectors,
        )

        detectors = _default_detectors(LintConfig(fuzzy_threshold=0.77))
        codes = {d.code for d in detectors}
        # PR 3 contributors:
        assert "LINT_FUZZY_DUP" in codes
        assert "LINT_STAGED_OVERLAP" in codes
        # PR 4 contributors:
        assert "LINT_REDUNDANT_DEP" in codes
        assert "LINT_ORPHAN" in codes

        fuzzy = next(d for d in detectors if isinstance(d, FuzzyTitleDupDetector))
        overlap = next(d for d in detectors if isinstance(d, StagedAdmittedOverlapDetector))
        assert fuzzy.threshold == 0.77
        assert overlap.threshold == 0.77

    def test_main_runs_default_detectors_against_bundled_example(self, capsys):
        from tools.knowledge.lint import main

        exit_code = main(["docs/knowledge"])
        captured = capsys.readouterr()
        # All default detectors emit only info-level on the bundled example, so
        # exit code stays 0 even though PR 4's RedundantDepDetector legitimately
        # surfaces two redundant-dep findings (real bugs in the bundled example,
        # tracked for a follow-up cleanup commit). No fuzzy/staged/orphan
        # findings at the default threshold.
        assert exit_code == 0
        assert "LINT_FUZZY_DUP" not in captured.out
        assert "LINT_STAGED_OVERLAP" not in captured.out
        assert "LINT_ORPHAN" not in captured.out
