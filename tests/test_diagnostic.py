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
