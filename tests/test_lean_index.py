from pathlib import Path

from tools.knowledge.lean_index import index_lean_project

LEAN_FIXTURES = Path(__file__).parent / "fixtures" / "lean"


class TestLeanIndex:
    def test_index_declarations(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert len(idx.declarations) > 0

    def test_finds_structure(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert "StrategicGame" in idx.declarations

    def test_finds_namespace_qualified(self):
        idx = index_lean_project(LEAN_FIXTURES)
        names = set(idx.declarations.keys())
        assert "StrategicGame.Profile" in names
        assert "StrategicGame.deviate" in names

    def test_finds_def(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert "StrategicGame.IsBestResponse" in idx.declarations
        assert "StrategicGame.IsNashEquilibrium" in idx.declarations

    def test_finds_theorem(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert "StrategicGame.IsNashEquilibrium.of_dominant" in idx.declarations
        decl = idx.declarations["StrategicGame.IsNashEquilibrium.of_dominant"]
        assert decl.kind == "theorem"

    def test_kind_is_canonical(self):
        idx = index_lean_project(LEAN_FIXTURES)
        for decl in idx.declarations.values():
            assert " " not in decl.kind, f"{decl.qualified_name} has non-canonical kind {decl.kind!r}"

    def test_sorry_detection(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert idx.sorry_decls == ["StrategicGame.IsNashEquilibrium.of_dominant"]

    def test_no_false_positive_sorry(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert not idx.declarations["StrategicGame.IsBestResponse"].has_sorry
        assert not idx.declarations["StrategicGame.IsNashEquilibrium"].has_sorry

    def test_modules(self):
        idx = index_lean_project(LEAN_FIXTURES)
        assert "GameTheoryLib.StrategicGame.Basic" in idx.modules
        assert "GameTheoryLib.StrategicGame.NashEquilibrium" in idx.modules

    def test_line_numbers(self):
        idx = index_lean_project(LEAN_FIXTURES)
        decl = idx.declarations["StrategicGame"]
        assert decl.line > 0
        assert decl.file.name == "Basic.lean"
