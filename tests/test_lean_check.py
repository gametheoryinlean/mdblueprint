from pathlib import Path

from tools.knowledge.lean_check import check_lean_references
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.models import LeanRef, Node

LEAN_FIXTURES = Path("tests/fixtures/lean")


def _make_idx():
    return index_lean_project(LEAN_FIXTURES)


class TestLeanChecks:
    def test_valid_references(self):
        idx = _make_idx()
        node = Node(
            id="test.valid",
            title="Valid",
            kind="definition",
            status="admitted",
            lean=LeanRef(
                modules=["GameTheoryLib.StrategicGame.Basic"],
                declarations=["StrategicGame"],
            ),
        )
        diags = check_lean_references([node], idx)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_missing_module(self):
        idx = _make_idx()
        node = Node(
            id="test.bad_module",
            title="Bad Module",
            kind="definition",
            status="admitted",
            lean=LeanRef(
                modules=["Nonexistent.Module"],
                declarations=["StrategicGame"],
            ),
        )
        diags = check_lean_references([node], idx)
        warnings = [d for d in diags if d.level == "warning"]
        assert any("Nonexistent.Module" in d.message for d in warnings)

    def test_missing_declaration(self):
        idx = _make_idx()
        node = Node(
            id="test.bad_decl",
            title="Bad Decl",
            kind="definition",
            status="admitted",
            lean=LeanRef(
                modules=["GameTheoryLib.StrategicGame.Basic"],
                declarations=["NonexistentDecl"],
            ),
        )
        diags = check_lean_references([node], idx)
        warnings = [d for d in diags if d.level == "warning"]
        assert any("NonexistentDecl" in d.message for d in warnings)

    def test_external_theorem_missing_is_error(self):
        idx = _make_idx()
        node = Node(
            id="test.ext",
            title="Ext",
            kind="external-theorem",
            status="admitted",
            lean=LeanRef(
                modules=["Nonexistent.Module"],
                declarations=["NonexistentDecl"],
            ),
        )
        diags = check_lean_references([node], idx)
        errors = [d for d in diags if d.level == "error"]
        assert len(errors) == 2

    def test_sorry_detection(self):
        idx = _make_idx()
        node = Node(
            id="test.sorry",
            title="Sorry",
            kind="theorem",
            status="admitted",
            lean=LeanRef(
                modules=["GameTheoryLib.StrategicGame.NashEquilibrium"],
                declarations=["IsNashEquilibrium.of_dominant"],
            ),
        )
        diags = check_lean_references([node], idx)
        warnings = [d for d in diags if d.level == "warning"]
        assert any("sorry" in d.message for d in warnings)

    def test_no_lean_section_skipped(self):
        idx = _make_idx()
        node = Node(id="test.no_lean", title="No Lean", kind="definition", status="admitted")
        diags = check_lean_references([node], idx)
        assert diags == []

    def test_qualified_name_match(self):
        idx = _make_idx()
        node = Node(
            id="test.qualified",
            title="Qualified",
            kind="definition",
            status="admitted",
            lean=LeanRef(
                modules=["GameTheoryLib.StrategicGame.Basic"],
                declarations=["Profile"],
            ),
        )
        diags = check_lean_references([node], idx)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []
