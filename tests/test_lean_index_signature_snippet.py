"""Regression tests: for `class`/`structure`/`inductive` (all
`where`-block openers), the signature snippet must include the block
body — the fields ARE the definition, so only showing the header
misrepresents the declaration.

For `def`/`theorem` the snippet stays cut just before `:=` as before.
"""
from pathlib import Path

from tools.knowledge.lean_index import index_lean_project


def test_class_signature_includes_where_block_body(tmp_path):
    lean_root = tmp_path / "lean"
    lean_root.mkdir(parents=True)
    (lean_root / "Foo.lean").write_text(
        "namespace Bar\n"
        "class MyCls (X : Type*) [PartialOrder X] where\n"
        "  /-- Dimension function. -/\n"
        "  dim : X → Nat\n"
        "  dim_lt : ∀ {E F : X}, E ≤ F → E ≠ F → dim E < dim F\n"
        "end Bar\n"
        "def other : Nat := 0\n"
    )
    idx = index_lean_project(lean_root)
    sig = idx.declarations["Bar.MyCls"].signature or ""
    assert "class MyCls" in sig, sig
    assert "dim : X" in sig, "field `dim` missing from class signature"
    assert "dim_lt" in sig, "field `dim_lt` missing from class signature"
    # Fields from OUTSIDE the where-block must not leak.
    assert "def other" not in sig, "signature leaked past the class body"


def test_structure_signature_includes_fields(tmp_path):
    lean_root = tmp_path / "lean"
    lean_root.mkdir(parents=True)
    (lean_root / "Foo.lean").write_text(
        "structure Datum where\n"
        "  a : Nat\n"
        "  b : Nat\n"
        "  P : a < b\n"
        "def next : Nat := 0\n"
    )
    idx = index_lean_project(lean_root)
    sig = idx.declarations["Datum"].signature or ""
    assert "structure Datum" in sig, sig
    assert "a : Nat" in sig and "b : Nat" in sig and "P : a < b" in sig, sig
    assert "def next" not in sig, "next decl leaked into structure signature"


def test_def_signature_still_cuts_at_walrus(tmp_path):
    lean_root = tmp_path / "lean"
    lean_root.mkdir(parents=True)
    (lean_root / "Foo.lean").write_text(
        "def one : Nat := 1\n"
        "def two : Nat :=\n"
        "  1 + 1\n"
    )
    idx = index_lean_project(lean_root)
    sig_one = idx.declarations["one"].signature or ""
    sig_two = idx.declarations["two"].signature or ""
    assert sig_one.endswith("Nat"), (
        f"def signature must cut just before `:=`, got {sig_one!r}"
    )
    assert "1 + 1" not in sig_one and "1 + 1" not in sig_two, (
        "def body leaked into signature"
    )


def test_class_signature_terminates_at_next_top_level(tmp_path):
    lean_root = tmp_path / "lean"
    lean_root.mkdir(parents=True)
    (lean_root / "Foo.lean").write_text(
        "class A where\n"
        "  x : Nat\n"
        "class B where\n"
        "  y : Nat\n"
    )
    idx = index_lean_project(lean_root)
    sig_a = idx.declarations["A"].signature or ""
    assert "class A" in sig_a
    assert "x : Nat" in sig_a
    assert "class B" not in sig_a, "signature leaked past class body"
    assert "y : Nat" not in sig_a
