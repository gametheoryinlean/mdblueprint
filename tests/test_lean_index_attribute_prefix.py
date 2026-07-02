"""Regression test: `@[simp] theorem foo` (and similar attribute-prefixed
declarations) must be indexed."""
from pathlib import Path

from tools.knowledge.lean_index import index_lean_project


def test_at_simp_theorem_is_indexed(tmp_path):
    lean_root = tmp_path / "lean"
    (lean_root).mkdir(parents=True)
    (lean_root / "Example.lean").write_text(
        "namespace Foo\n"
        "@[simp] theorem bar (n : Nat) : n + 0 = n := by simp\n"
        "@[simp, norm_cast] theorem baz : True := trivial\n"
        "theorem plain : True := trivial\n"
        "end Foo\n"
    )
    idx = index_lean_project(lean_root)
    assert "Foo.bar" in idx.declarations, (
        "@[simp] theorem was silently missed by the index"
    )
    assert "Foo.baz" in idx.declarations, (
        "multi-attribute @[simp, norm_cast] theorem was missed"
    )
    assert "Foo.plain" in idx.declarations, (
        "sanity: plain theorem still indexed"
    )
    # Kinds should be canonical.
    assert idx.declarations["Foo.bar"].kind == "theorem"
    assert idx.declarations["Foo.baz"].kind == "theorem"


def test_at_attribute_def_is_indexed(tmp_path):
    """Also cover `@[reducible] def` and similar."""
    lean_root = tmp_path / "lean"
    (lean_root).mkdir(parents=True)
    (lean_root / "Example.lean").write_text(
        "namespace Foo\n"
        "@[reducible] def alias : Nat := 0\n"
        "end Foo\n"
    )
    idx = index_lean_project(lean_root)
    assert "Foo.alias" in idx.declarations
    assert idx.declarations["Foo.alias"].kind == "def"
