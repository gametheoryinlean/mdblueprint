# Blueprint Lint PR 2 — Orchestrator Skeleton + CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `mdblueprint-lint` — a Python orchestrator with the `Detector` protocol, `Linter` engine, text/JSON renderers, and a CLI — with zero real detectors. Running it against the bundled example must exit 0 with "no findings".

**Architecture:** One new module `tools/knowledge/lint.py` holds the protocol, the engine, the renderers, the Claude-subprocess runner factory, and `main(argv)`. Tests construct fake detectors and inject them through the constructor to verify the pipeline end-to-end without touching `claude` or any LLM. Real detectors come in PR 3–7 and plug in via the same `Detector` protocol.

**Tech Stack:** Python 3.10+, stdlib (`argparse`, `dataclasses`, `json`, `subprocess`, `typing.Protocol`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 2 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PR 1 already shipped: `tools.knowledge.validator.Diagnostic` now has `code: str | None` and `related: tuple[str, ...]`, and accepts `"info"` as `level`. PR 2 builds on that.

Real APIs the orchestrator wires together (do not reimplement):

- `tools.knowledge.parser.scan_directory(root: Path) -> list[Node]` — reads `.md` nodes under a directory.
- `tools.knowledge.graph.build_graph(nodes: list[Node]) -> tuple[KnowledgeGraph, list[Diagnostic]]` — builds the dependency graph and surfaces cycle/missing-dep diagnostics.
- Node convention: a knowledge root contains `nodes/` (admitted) and `staged/` (under review). Loaders must scan both, as `tools.knowledge.check.check_knowledge_base` does.

The `LlmRunner` shape mirrors `tools.knowledge.proof_fill.CodexRunner`: a callable `Callable[[str], str]` taking a prompt and returning the model's text. PR 6+ detectors will use it; PR 2 only defines the type and a factory that builds one from `subprocess.run(["claude", "-p", ...])`.

## File Structure

- **Create**: `tools/knowledge/lint.py` — the entire orchestrator. Target ≤ 250 lines; if it crosses ~300, that's a signal to split, but it should not in PR 2.
- **Create**: `tests/test_lint_orchestrator.py` — covers `Linter`, renderers, and `main()` end-to-end via fake detectors.
- **Modify**: `pyproject.toml` — add `mdblueprint-lint = "tools.knowledge.lint:main"` under `[project.scripts]`.

No other module is touched. No new dependency is added.

---

### Task 1: Linter core (`LlmRunner`, `Detector`, `Linter.run`)

**Files:**
- Create: `tools/knowledge/lint.py`
- Create: `tests/test_lint_orchestrator.py`

#### Step 1.1: Write the first failing tests

- [ ] Create `tests/test_lint_orchestrator.py` with this initial content:

```python
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
```

#### Step 1.2: Run the new tests and verify they fail (module missing)

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py -v`
- [ ] Expected: collection error: `ModuleNotFoundError: No module named 'tools.knowledge.lint'`.

#### Step 1.3: Create the minimal `lint.py` to satisfy Task 1 tests

- [ ] Create `tools/knowledge/lint.py` with this content. Do not add anything beyond what Task 1 needs; renderers and `main()` come in later tasks.

```python
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
```

#### Step 1.4: Run the Task 1 tests and verify they pass

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py -v`
- [ ] Expected: 5 tests pass (the three under `TestLinterRun` and the two under `TestLinterLlmGating`).

#### Step 1.5: Run the full suite and confirm no regressions

- [ ] Run: `uv run --extra dev python -m pytest -q`
- [ ] Expected: every previously-passing test still passes. The total count climbs by 5 (PR 1 finished at 514; expect 519 now).

#### Step 1.6: Commit Task 1

- [ ] Stage and commit. **Do NOT add a `Co-Authored-By` trailer** — attribution is disabled in this repo's environment.

```bash
git add tools/knowledge/lint.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): add Linter orchestrator + Detector protocol

First piece of the blueprint-lint orchestrator (issue #121, PR 2).
Defines the Detector Protocol, the LlmRunner type alias, and a Linter
class that loads nodes, builds the graph, and runs detectors. No real
detectors yet — those land in PR 3+.
EOF
)"
```

---

### Task 2: Renderers (`render_text`, `render_json`)

**Files:**
- Modify: `tools/knowledge/lint.py` (append two render functions)
- Modify: `tests/test_lint_orchestrator.py` (append a `TestRenderers` class)

#### Step 2.1: Write failing tests for the renderers

- [ ] Append to `tests/test_lint_orchestrator.py`:

```python
# ── Renderers ─────────────────────────────────────────────────────────────────

import json

from tools.knowledge.lint import render_json, render_text


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
```

#### Step 2.2: Run the new tests and verify they fail

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py::TestRenderText tests/test_lint_orchestrator.py::TestRenderJson -v`
- [ ] Expected: import errors — `render_text` and `render_json` don't exist yet.

#### Step 2.3: Implement the renderers

- [ ] Append to `tools/knowledge/lint.py`:

```python
import json as _json


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
```

#### Step 2.4: Run the renderer tests and verify they pass

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py::TestRenderText tests/test_lint_orchestrator.py::TestRenderJson -v`
- [ ] Expected: 6 tests pass.

#### Step 2.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest -q`
- [ ] Expected: total count is 525 (519 + 6). All pass.

#### Step 2.6: Commit Task 2

```bash
git add tools/knowledge/lint.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): add text and JSON renderers for diagnostics

render_text groups findings by rule code (stable sorted) with an
"uncoded" bucket for non-lint diagnostics. render_json emits a flat,
stable JSON array carrying all Diagnostic fields. Issue #121, PR 2.
EOF
)"
```

---

### Task 3: CLI entry point + Claude runner factory + smoke test

**Files:**
- Modify: `tools/knowledge/lint.py` (append `_make_claude_cli_runner` and `main`)
- Modify: `tests/test_lint_orchestrator.py` (append a `TestCli` class)
- Modify: `pyproject.toml` (add `mdblueprint-lint` script entry)

#### Step 3.1: Write failing tests for the CLI

- [ ] Append to `tests/test_lint_orchestrator.py`:

```python
# ── CLI ───────────────────────────────────────────────────────────────────────

from tools.knowledge.lint import _make_claude_cli_runner, main


class TestCli:
    def test_smoke_no_detectors_exits_zero_with_no_findings(
        self, tmp_path, capsys, monkeypatch
    ):
        root = _make_minimal_knowledge_root(tmp_path)
        # The default detector list (built inside main) is empty in PR 2.
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
            "tools.knowledge.lint._default_detectors", lambda: [det]
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
            "tools.knowledge.lint._default_detectors", lambda: [det]
        )
        rc = main([str(root)])
        assert rc == 0

    def test_json_output_parses(self, tmp_path, capsys, monkeypatch):
        root = _make_minimal_knowledge_root(tmp_path)
        det = _emit_one_warning()
        monkeypatch.setattr(
            "tools.knowledge.lint._default_detectors", lambda: [det]
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
            "tools.knowledge.lint._default_detectors", lambda: [det]
        )
        rc = main([str(root)])
        assert rc == 0
        assert det.last_call is None


class TestClaudeRunnerFactory:
    def test_factory_returns_callable_without_calling_subprocess(self):
        runner = _make_claude_cli_runner(model="claude-sonnet-4-6")
        assert callable(runner)
        # Calling runner() would actually invoke `claude`; we only verify shape.
```

#### Step 3.2: Run the new tests and verify they fail

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py::TestCli tests/test_lint_orchestrator.py::TestClaudeRunnerFactory -v`
- [ ] Expected: import errors — `main` and `_make_claude_cli_runner` don't exist yet.

#### Step 3.3: Implement `main`, `_default_detectors`, and the Claude runner factory

- [ ] Append to `tools/knowledge/lint.py`:

```python
import argparse
import subprocess
import sys


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
    ap.add_argument("--llm", action="store_true",
                    help="Enable LLM-backed detectors (calls `claude -p`).")
    ap.add_argument("--no-llm", action="store_true",
                    help="Explicitly disable LLM-backed detectors (default).")
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
    if args.strict_warnings and any(d.level == "warning" for d in diags):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

#### Step 3.4: Run the CLI tests and verify they pass

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py -v`
- [ ] Expected: every test in the file passes (5 from Task 1 + 6 from Task 2 + 6 from Task 3 = 17 total).

#### Step 3.5: Register the `mdblueprint-lint` entry point

- [ ] Edit `pyproject.toml`. Find the `[project.scripts]` table and add `mdblueprint-lint = "tools.knowledge.lint:main"` while preserving alphabetical-or-existing order. The relevant block must end up looking like:

```toml
[project.scripts]
mdblueprint-check = "tools.knowledge.check:main"
mdblueprint-econcslib-gate = "tools.knowledge.econcslib_gate:main"
mdblueprint-lean-alignment = "tools.knowledge.lean_alignment:main"
mdblueprint-lean-link-candidates = "tools.knowledge.lean_link_candidates:main"
mdblueprint-lean-linking = "tools.knowledge.lean_linking:main"
mdblueprint-lint = "tools.knowledge.lint:main"
mdblueprint-proof-fill = "tools.knowledge.proof_fill:main"
mdblueprint-publish = "tools.knowledge.publish:main"
mdblueprint-render-check = "tools.knowledge.render_check:main"
mdblueprint-serve = "tools.knowledge.serve:main"
```

Note: if the existing file is grouped non-alphabetically, simply insert the new line in alphabetical position relative to its siblings; don't reshuffle the others.

#### Step 3.6: Re-install the project so the new console script is wired up

- [ ] Run: `uv sync --extra dev 2>&1 | tail -5`
- [ ] Expected: a brief "resolved … installed …" summary, no errors. `uv sync` re-runs setuptools and updates the entry-point table.

#### Step 3.7: Run the end-to-end smoke against `docs/knowledge`

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: prints `✅ No lint findings.` and exits 0.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --json`
- [ ] Expected: prints `[]` and exits 0.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --strict-warnings`
- [ ] Expected: exit 0 (no warnings to promote since detector list is empty).

#### Step 3.8: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest -q`
- [ ] Expected: 531 total (525 + 6), all pass.

#### Step 3.9: Confirm `mdblueprint-check` output is byte-identical

- [ ] Capture before and after on the bundled example. Because no file the `check` command depends on was modified in PR 2, the diff should be empty.

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output.

#### Step 3.10: Commit Task 3

```bash
git add tools/knowledge/lint.py tests/test_lint_orchestrator.py pyproject.toml
git commit -m "$(cat <<'EOF'
feat(lint): add mdblueprint-lint CLI entry point

argparse-driven main() wires Linter + renderers + an optional Claude
subprocess runner together. Default detector list is empty; PR 3+
populates it via Detector implementations. Registers the
mdblueprint-lint console script. Issue #121, PR 2.
EOF
)"
```

- [ ] Run `git status --short --branch` and confirm a clean tree on `feat/lint-pr2-orchestrator` with 3 new commits ahead of origin/main.

---

## Definition of Done

- [ ] `tools/knowledge/lint.py` exists, ≤ 250 lines, defines `LlmRunner`, `Detector`, `Linter`, `_default_detectors`, `_make_claude_cli_runner`, `render_text`, `render_json`, `_build_arg_parser`, and `main`.
- [ ] `tests/test_lint_orchestrator.py` exists with at least 17 passing tests across `TestLinterRun`, `TestLinterLlmGating`, `TestRenderText`, `TestRenderJson`, `TestCli`, `TestClaudeRunnerFactory`.
- [ ] `pyproject.toml` has `mdblueprint-lint = "tools.knowledge.lint:main"` under `[project.scripts]`.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0 and prints "No lint findings".
- [ ] `uv run --extra dev python -m pytest -q` is fully green.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` output unchanged.
- [ ] Three commits on `feat/lint-pr2-orchestrator` (Linter core, renderers, CLI), no `Co-Authored-By` trailers.

## Hand-off to PR 3

PR 3 (fuzzy title/statement dup + staged↔admitted overlap) populates `_default_detectors()` for the first time and introduces a configurable threshold via `mdblueprint.yml`. It depends only on what PR 2 ships above; no further changes to the orchestrator are needed.
