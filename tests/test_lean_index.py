from pathlib import Path

from tools.knowledge.config import LeanRepositoryConfig
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

    def test_configured_repository_adds_source_metadata(self):
        repo = LeanRepositoryConfig(
            id="main",
            title="Example Lean Library",
            local_path=LEAN_FIXTURES,
            web_url="https://example.test/org/repo",
            source_url_template="{web_url}/blob/{revision}/{path}#L{line}",
            revision="abc123",
        )

        idx = index_lean_project(LEAN_FIXTURES, repository=repo)
        decl = idx.declarations["StrategicGame"]

        assert decl.repository_id == "main"
        assert decl.repository_title == "Example Lean Library"
        assert decl.revision == "abc123"
        assert decl.relative_path == "GameTheoryLib/StrategicGame/Basic.lean"
        assert decl.source_url == (
            "https://example.test/org/repo/blob/abc123/"
            "GameTheoryLib/StrategicGame/Basic.lean#L3"
        )

    def test_repository_subdir_prepended_to_path(self):
        """When `subdir` is set, the template `{path}` placeholder receives
        the prefixed path so users with a `lean/` subdir don't need to
        hardcode the prefix in source_url_template."""
        repo = LeanRepositoryConfig(
            id="main",
            title="Example Lean Library",
            local_path=LEAN_FIXTURES,
            web_url="https://example.test/org/repo",
            source_url_template="{web_url}/blob/{revision}/{path}#L{line}",
            revision="abc123",
            subdir="lean",
        )

        idx = index_lean_project(LEAN_FIXTURES, repository=repo)
        decl = idx.declarations["StrategicGame"]

        # relative_path stays clean (within local_path), but source_url
        # includes the subdir prefix.
        assert decl.relative_path == "GameTheoryLib/StrategicGame/Basic.lean"
        assert decl.source_url == (
            "https://example.test/org/repo/blob/abc123/"
            "lean/GameTheoryLib/StrategicGame/Basic.lean#L3"
        )

    def test_repository_subdir_empty_keeps_backcompat(self):
        """Default empty subdir behaves like before (no prefix)."""
        repo = LeanRepositoryConfig(
            id="main",
            title="Example Lean Library",
            local_path=LEAN_FIXTURES,
            web_url="https://example.test/org/repo",
            source_url_template="{web_url}/blob/{revision}/{path}#L{line}",
            revision="abc123",
        )
        idx = index_lean_project(LEAN_FIXTURES, repository=repo)
        decl = idx.declarations["StrategicGame"]
        assert "/lean/" not in decl.source_url
        assert decl.source_url == (
            "https://example.test/org/repo/blob/abc123/"
            "GameTheoryLib/StrategicGame/Basic.lean#L3"
        )

    def test_duplicate_warning_includes_repository_source_metadata(self, tmp_path):
        (tmp_path / "A.lean").write_text("theorem Dup : True := True.intro\n", encoding="utf-8")
        (tmp_path / "B.lean").write_text("theorem Dup : True := True.intro\n", encoding="utf-8")
        repo = LeanRepositoryConfig(
            id="main",
            title="Example Lean Library",
            local_path=tmp_path,
            web_url="https://example.test/org/repo",
            source_url_template="{web_url}/blob/{revision}/{path}#L{line}",
            revision="abc123",
        )

        idx = index_lean_project(tmp_path, repository=repo)

        assert len(idx.warnings) == 1
        warning = idx.warnings[0]
        assert "main@abc123" in warning
        assert "A.lean:1" in warning
        assert "B.lean:1" in warning

    def test_extracts_signature_docstring_module_and_namespace(self, tmp_path):
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example" / "Rich.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
namespace Example

/-- A documented predicate. -/
def IsGood
    (n : Nat) : Prop :=
  n = n

structure Fancy where
  value : Nat

end Example
""".strip() + "\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)

        decl = idx.declarations["Example.IsGood"]
        assert decl.module == "Example.Rich"
        assert decl.namespace == "Example"
        assert decl.docstring == "A documented predicate."
        assert "def IsGood" in decl.signature
        assert "(n : Nat) : Prop" in decl.signature
        assert ":=" not in decl.signature
        assert idx.declarations["Example.Fancy"].kind == "structure"
        assert "structure Fancy where" in idx.declarations["Example.Fancy"].signature

    def test_sections_do_not_qualify_declaration_names(self, tmp_path):
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
section helper_section

def sectionLocalName : True := True.intro

end helper_section

namespace RealNamespace

section inner

theorem namespacedOnly : True := True.intro

end inner

end RealNamespace
""".strip() + "\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)

        assert "sectionLocalName" in idx.declarations
        assert "helper_section.sectionLocalName" not in idx.declarations
        assert "RealNamespace.namespacedOnly" in idx.declarations
        assert "RealNamespace.inner.namespacedOnly" not in idx.declarations
