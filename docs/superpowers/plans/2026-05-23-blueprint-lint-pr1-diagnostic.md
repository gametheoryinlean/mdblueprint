# Blueprint Lint PR 1 — Diagnostic Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `tools.knowledge.validator.Diagnostic` with two optional fields (`code`, `related`) and accept a new `level` value (`"info"`) so subsequent lint PRs have a place to put rule-coded findings. Behavior of `check` and all existing consumers must be unchanged.

**Architecture:** Purely additive change to one `@dataclass`. New fields default to `None` / `()`. `__str__` gains a `[CODE]` segment only when `code` is set, so existing string output for every current call site is byte-for-byte identical. No new dependencies.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`, pytest.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 1 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

`Diagnostic` is the project's single error/warning carrier; 30+ call sites in `tools/knowledge/` construct it with positional args `(level, node_id, message, file_path)`. The current shape:

```python
# tools/knowledge/validator.py:30-39
@dataclass
class Diagnostic:
    level: str  # "error" or "warning"
    node_id: str
    message: str
    file_path: Path | None = None

    def __str__(self) -> str:
        loc = f"{self.file_path} ({self.node_id})" if self.file_path else self.node_id
        return f"[{self.level.upper()}] {loc}: {self.message}"
```

Existing test coverage of `Diagnostic` itself lives in `tests/test_validator.py:215-224` (class `TestDiagnosticStr`, 2 tests). Those tests stay green after this PR.

## File Structure

- **Modify**: `tools/knowledge/validator.py` — extend `Diagnostic` dataclass and `__str__`.
- **Create**: `tests/test_diagnostic.py` — focused tests for the new fields, the new level, and backward-compat. Separated from `test_validator.py` because the `Diagnostic` surface is growing beyond a 2-test inner class.

No other module is touched. All 30+ existing `Diagnostic(...)` call sites continue to work because new fields are optional with defaults.

---

### Task 1: Extend `Diagnostic` with `code`, `related`, and `info` level

**Files:**
- Modify: `tools/knowledge/validator.py:30-39`
- Create: `tests/test_diagnostic.py`

#### Step 1.1: Write failing tests

- [ ] Create `tests/test_diagnostic.py` with the full test file below.

```python
"""Tests for the Diagnostic dataclass extension (lint PR 1)."""
from __future__ import annotations

from pathlib import Path

from tools.knowledge.validator import Diagnostic


class TestDiagnosticDefaults:
    def test_code_defaults_to_none(self):
        d = Diagnostic("error", "n.x", "msg")
        assert d.code is None

    def test_related_defaults_to_empty_tuple(self):
        d = Diagnostic("error", "n.x", "msg")
        assert d.related == ()

    def test_file_path_default_unchanged(self):
        d = Diagnostic("error", "n.x", "msg")
        assert d.file_path is None


class TestDiagnosticInfoLevel:
    def test_info_level_str_uppercased(self):
        d = Diagnostic("info", "n.x", "msg")
        assert str(d) == "[INFO] n.x: msg"

    def test_info_level_with_file_path(self):
        d = Diagnostic("info", "n.x", "msg", Path("foo.md"))
        assert str(d) == "[INFO] foo.md (n.x): msg"


class TestDiagnosticCodeInStr:
    def test_code_segment_appears_when_set(self):
        d = Diagnostic("warning", "n.x", "msg", code="LINT_FUZZY_DUP")
        assert str(d) == "[WARNING][LINT_FUZZY_DUP] n.x: msg"

    def test_code_segment_with_file_path(self):
        d = Diagnostic("info", "n.x", "msg", Path("foo.md"), code="LINT_ORPHAN")
        assert str(d) == "[INFO][LINT_ORPHAN] foo.md (n.x): msg"

    def test_code_segment_absent_when_unset(self):
        d = Diagnostic("error", "n.x", "msg")
        assert "[LINT_" not in str(d)
        assert str(d) == "[ERROR] n.x: msg"


class TestDiagnosticRelated:
    def test_related_pair_held_as_tuple(self):
        d = Diagnostic(
            "warning", "n.a", "duplicate of n.b",
            code="LINT_FUZZY_DUP", related=("n.b",),
        )
        assert d.related == ("n.b",)
        assert d.code == "LINT_FUZZY_DUP"

    def test_related_does_not_appear_in_str(self):
        # related is consumed by --json / structured renderers, not __str__.
        d = Diagnostic("warning", "n.a", "m", code="LINT_X", related=("n.b", "n.c"))
        assert "n.b" not in str(d)
        assert "n.c" not in str(d)


class TestDiagnosticBackwardCompat:
    """Existing 30+ call sites construct Diagnostic positionally with up to 4 args.
    Verify those exact shapes still build and stringify identically."""

    def test_three_arg_positional_unchanged(self):
        d = Diagnostic("error", "n.x", "missing field")
        assert str(d) == "[ERROR] n.x: missing field"

    def test_four_arg_positional_unchanged(self):
        d = Diagnostic("warning", "n.x", "alignment off", Path("a/b.md"))
        assert str(d) == "[WARNING] a/b.md (n.x): alignment off"
```

#### Step 1.2: Run the new tests and verify they fail

- [ ] Run: `uv run --extra dev python -m pytest tests/test_diagnostic.py -v`
- [ ] Expected outcome:
  - `TestDiagnosticDefaults::test_code_defaults_to_none` → **FAIL** with `AttributeError: 'Diagnostic' object has no attribute 'code'`
  - `TestDiagnosticDefaults::test_related_defaults_to_empty_tuple` → **FAIL** same reason
  - `TestDiagnosticInfoLevel::*` → **PASS** (current `__str__` already uppercases any level)
  - `TestDiagnosticCodeInStr::*` (the first two) → **FAIL** (code segment not added yet)
  - `TestDiagnosticRelated::*` → **FAIL** (no `related` attr)
  - `TestDiagnosticBackwardCompat::*` → **PASS** (current code already supports these shapes)

The mix of fails and passes is the expected starting state.

#### Step 1.3: Implement the extension

- [ ] Edit `tools/knowledge/validator.py:30-39`. Replace the existing `Diagnostic` block with:

```python
@dataclass
class Diagnostic:
    level: str  # "error", "warning", or "info"
    node_id: str
    message: str
    file_path: Path | None = None
    code: str | None = None
    related: tuple[str, ...] = ()

    def __str__(self) -> str:
        loc = f"{self.file_path} ({self.node_id})" if self.file_path else self.node_id
        code_segment = f"[{self.code}]" if self.code else ""
        return f"[{self.level.upper()}]{code_segment} {loc}: {self.message}"
```

Three things to verify visually before saving:

1. The two new fields have defaults — every existing positional `Diagnostic(level, node_id, message, file_path)` call still type-checks and builds.
2. `code_segment` is the empty string when `code` is `None`, so `f"[{self.level.upper()}]{code_segment} {loc}: ..."` collapses to `f"[{self.level.upper()}] {loc}: ..."` — byte-identical to the old format.
3. The comment on `level` mentions `info` so future readers know it is a valid value.

#### Step 1.4: Run the new tests and verify they all pass

- [ ] Run: `uv run --extra dev python -m pytest tests/test_diagnostic.py -v`
- [ ] Expected outcome: 12 tests, all PASS.

#### Step 1.5: Run the full suite and confirm zero regressions

- [ ] Run: `uv run --extra dev python -m pytest -q`
- [ ] Expected outcome: every previously-passing test still passes. In particular, `tests/test_validator.py::TestDiagnosticStr::*` (the 2 existing string tests) still PASS unchanged.
- [ ] If any test fails: revert the dataclass change, re-read the failure, and check whether `__str__` produced a different string for the no-`code` case. The exact format must match `[LEVEL] <loc>: <message>` byte-for-byte.

#### Step 1.6: Confirm `mdblueprint-check` output is byte-identical

- [ ] Capture before and after, against the bundled example knowledge base.

```bash
# Re-run on the working tree (post-change) and compare to a baseline from main.
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected outcome: `diff` exits 0 with no output. The user-visible CLI behavior of `check` is unchanged because no current call site sets `code`.
- [ ] If `git stash` reports "No local changes to save", that means `tests/test_diagnostic.py` was already committed in an earlier attempt — stash both the test file and the validator change together (`git stash -u`) and re-run.

#### Step 1.7: Commit

- [ ] Stage and commit only the two files relevant to this PR. Use a HEREDOC for the message and follow the repo's `<type>(<scope>): <subject>` style seen in `git log -5`:

```bash
git add tools/knowledge/validator.py tests/test_diagnostic.py
git commit -m "$(cat <<'EOF'
feat(lint): add code and related fields to Diagnostic, accept info level

Pure additive change: existing 30+ Diagnostic call sites unaffected
because new fields default to None / empty tuple, and __str__ emits
the new [CODE] segment only when code is set. Prepares ground for
the blueprint-lint orchestrator (issue #121, PR 1 of 8).
EOF
)"
```

- [ ] Run `git status --short --branch` and confirm the working tree is clean and the branch is exactly 1 commit ahead of where it was.

---

## Definition of Done

- [ ] `tests/test_diagnostic.py` exists with 12 passing tests.
- [ ] `tools/knowledge/validator.Diagnostic` has `code: str | None = None` and `related: tuple[str, ...] = ()` fields.
- [ ] `__str__` emits `[CODE]` only when `code` is non-`None`.
- [ ] `uv run --extra dev python -m pytest -q` is fully green.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` output is byte-identical to pre-change.
- [ ] One commit landed with the message above.

## Hand-off to PR 2

PR 2 (orchestrator skeleton) imports `Diagnostic` and constructs it with the new keyword args. No further changes to `validator.py` are needed in PR 2.
