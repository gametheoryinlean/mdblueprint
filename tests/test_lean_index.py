from pathlib import Path

from tools.knowledge.config import LeanRepositoryConfig
from tools.knowledge.lean_index import LeanIndex, index_lean_project, suggest_for_unresolved

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
        # `def` bodies short enough to fit within the body look-ahead
        # cap are now inlined (previously always cut at `:=`).
        assert ":=" in decl.signature
        assert "n = n" in decl.signature
        assert idx.declarations["Example.Fancy"].kind == "structure"
        assert "structure Fancy where" in idx.declarations["Example.Fancy"].signature

    def test_abbrev_shows_rhs(self, tmp_path):
        """Regression: `abbrev` should include the RHS of `:=`.

        Truncating an alias like `abbrev OrbitCat := X` at `:=` erases
        the definition — the reader is left with a header that says
        nothing about what the alias resolves to.
        """
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "abbrev OrbitCat (G X : Type*) : Type _ := X\n"
            "\n"
            "abbrev Multi (X : Type*) : Type _ :=\n"
            "  MyWrapper (X × X)\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)

        sig1 = idx.declarations["OrbitCat"].signature
        assert sig1 == "abbrev OrbitCat (G X : Type*) : Type _ := X"

        sig2 = idx.declarations["Multi"].signature
        assert "abbrev Multi (X : Type*) : Type _ :=" in sig2
        assert "MyWrapper (X × X)" in sig2

    def test_def_shows_short_body(self, tmp_path):
        """Compact `def` bodies (up to ~4 lines) should be inlined.

        For a one-liner subtype definition like `def Mor := {g // p g}`,
        cutting at `:=` hides the whole point of the declaration.
        """
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "def Mor (E E' : OrbitCat G X) : Type _ :=\n"
            "  {g : G // g • (E : X) ≤ (E' : X)}\n"
            "\n"
            "def oneLiner (n : Nat) : Nat := n + 1\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)

        sig_mor = idx.declarations["Mor"].signature
        assert "def Mor (E E' : OrbitCat G X) : Type _ :=" in sig_mor
        assert "{g : G // g • (E : X) ≤ (E' : X)}" in sig_mor

        sig_one = idx.declarations["oneLiner"].signature
        assert sig_one == "def oneLiner (n : Nat) : Nat := n + 1"

    def test_def_with_long_body_still_cuts(self, tmp_path):
        """A `def` whose body exceeds the look-ahead cap falls back to
        cutting at `:=` — we don't want to inline sprawling
        implementations or long tactic proofs."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "def big : Nat := by\n"
            "  have h1 := someLemma\n"
            "  have h2 := otherLemma\n"
            "  have h3 := thirdLemma\n"
            "  have h4 := fourthLemma\n"
            "  have h5 := fifthLemma\n"
            "  exact h1 + h2 + h3 + h4 + h5\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)
        sig = idx.declarations["big"].signature

        # We only guarantee the header appears; the body should be cut.
        assert sig.startswith("def big : Nat")
        assert "someLemma" not in sig
        assert "exact" not in sig

    def test_theorem_never_shows_body(self, tmp_path):
        """`theorem` continues to hide `:=` bodies regardless of length —
        even a one-line proof should be truncated, so blueprint readers
        see the statement, not the proof strategy."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "theorem trivial : True := True.intro\n"
            "\n"
            "theorem alsoTrivial : True := by exact True.intro\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)

        sig1 = idx.declarations["trivial"].signature
        assert sig1 == "theorem trivial : True"
        assert "True.intro" not in sig1

        sig2 = idx.declarations["alsoTrivial"].signature
        assert sig2 == "theorem alsoTrivial : True"
        assert "exact" not in sig2

    def test_named_argument_walrus_does_not_truncate_signature(self, tmp_path):
        """Regression: `(name := value)` inside signature must not be treated as `:=`.

        In Lean 4, named-argument syntax `(G := G)` uses the `:=` token but
        is *nested* inside brackets and does not open a definition body.
        `_signature_snippet` must skip it and keep reading until the real
        top-level `:=` or the header terminator (`where` / next decl).
        """
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "structure PXPrimeOrbitCat {X' : Type*}\n"
            "    (_d : InductionDatum (G := G) X') : Type _ where\n"
            "  cell : X'\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)
        sig = idx.declarations["PXPrimeOrbitCat"].signature

        # The named-arg `(G := G)` must appear intact in the snippet.
        assert "(G := G)" in sig, sig
        # The header must extend to the `where` line and include the
        # structure body (fields are the definition, see design intent
        # in `_signature_snippet`).
        assert "Type _ where" in sig, sig
        assert "cell : X'" in sig, sig

    def test_theorem_where_block_does_not_expose_proof(self, tmp_path):
        """Regression: `theorem : ... where field := by <tactics>` must not
        surface the proof body.  Only `structure`/`class`/`inductive`/
        `instance`/`def`/`abbrev` extend into a `where` block; for
        `theorem`/`lemma`/`example` the block is a tactic proof."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "theorem essSurj :\n"
            "    F.EssSurj where\n"
            "  mem_essImage q := by\n"
            "    obtain ⟨g, E, hq⟩ := helper q\n"
            "    exact ⟨E, ⟨someIso g E⟩⟩\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)
        sig = idx.declarations["essSurj"].signature

        # Statement is present.
        assert "theorem essSurj" in sig
        assert "F.EssSurj where" in sig
        # Proof body is NOT surfaced.
        assert "mem_essImage" not in sig, sig
        assert "obtain" not in sig, sig
        assert "by" not in sig.split("where", 1)[1] if "where" in sig else True

    def test_instance_where_block_is_still_included(self, tmp_path):
        """Instances remain expanded — the field assignments *are* the
        definition (mirrors the pre-existing behaviour on e.g.
        `scoped instance category : Category X where Hom := ...`)."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "instance category : Category X where\n"
            "  Hom E E' := Mor E E'\n"
            "  id E := Mor.id E\n"
            "  comp α β := Mor.comp α β\n",
            encoding="utf-8",
        )

        idx = index_lean_project(lean_root)
        sig = idx.declarations["category"].signature

        assert "instance category : Category X where" in sig
        assert "Hom E E' := Mor E E'" in sig
        assert "comp α β := Mor.comp α β" in sig

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


class TestSuggestForUnresolved:
    @staticmethod
    def _index_from(decls: list[str], modules: list[str] | None = None) -> LeanIndex:
        idx = LeanIndex()
        from tools.knowledge.lean_index import LeanDeclaration

        for qualified in decls:
            name = qualified.rsplit(".", 1)[-1]
            namespace = qualified.rsplit(".", 1)[0] if "." in qualified else None
            idx.declarations[qualified] = LeanDeclaration(
                name=name,
                qualified_name=qualified,
                kind="def",
                file=Path("/tmp/fake.lean"),
                line=1,
                module=namespace,
                namespace=namespace,
            )
        for mod in modules or []:
            idx.modules[mod] = Path(f"/tmp/{mod.replace('.', '/')}.lean")
        return idx

    def test_empty_index_returns_no_suggestions(self):
        assert suggest_for_unresolved("Foo.bar", LeanIndex()) == []

    def test_suffix_match_prioritised(self):
        idx = self._index_from([
            "Foo.bar",
            "Other.Namespace.bar",
            "Unrelated.qux",
        ])
        out = suggest_for_unresolved("bar", idx)
        assert "Foo.bar" in out
        assert "Other.Namespace.bar" in out

    def test_module_match_surfaces_as_marker(self):
        idx = self._index_from([], modules=["Foo.Bar"])
        out = suggest_for_unresolved("Foo.Bar", idx)
        assert "(module) Foo.Bar" in out

    def test_token_overlap_fallback(self):
        idx = self._index_from([
            "Namespace.multiplicativeGroup",
            "Namespace.additiveGroup",
            "Namespace.unrelated",
        ])
        out = suggest_for_unresolved("multiplicative_group_scheme", idx)
        # multiplicativeGroup shares both 'multiplicative' and 'group' tokens
        assert any("multiplicativeGroup" in s for s in out)

    def test_limit_k(self):
        idx = self._index_from([f"Ns.fooBar{i}" for i in range(10)])
        out = suggest_for_unresolved("fooBar1", idx, k=3)
        assert len(out) == 3

    def test_no_tokens_no_suggestions(self):
        idx = self._index_from(["Namespace.realDecl"])
        # A name with no tokens (only punctuation) yields nothing
        assert suggest_for_unresolved(".", idx) == []


class TestBlueprintMarkers:
    def test_module_level_blueprint_inherits(self, tmp_path):
        """A `## Blueprint` section in the module docstring is attached
        to every declaration in that module."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
/-!
# Module title

Body.

## Blueprint

`topic.foo` and also `topic.bar`.
-/

namespace Example

def first : Nat := 1
def second : Nat := 2

end Example
""".strip() + "\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        assert idx.declarations["Example.first"].blueprint_nodes == ("topic.foo", "topic.bar")
        assert idx.declarations["Example.second"].blueprint_nodes == ("topic.foo", "topic.bar")

    def test_declaration_level_marker_overrides_module_level(self, tmp_path):
        """Per-declaration `Blueprint:` marker fully replaces the
        module-level `## Blueprint` section. Without per-decl marker,
        the declaration inherits the module-level list."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
/-!
# Module

## Blueprint

`topic.module_default`
-/

/-- Specific declaration.

Blueprint: topic.specific
-/
def first : Nat := 1

def second : Nat := 2
""".strip() + "\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        # `first` has its own marker -> module-level is replaced, not unioned.
        assert idx.declarations["first"].blueprint_nodes == ("topic.specific",)
        # `second` has no per-decl marker -> inherits module-level.
        assert idx.declarations["second"].blueprint_nodes == ("topic.module_default",)

    def test_no_markers_yields_empty_tuple(self, tmp_path):
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            "/-- A plain declaration. -/\ndef plain : Nat := 0\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        assert idx.declarations["plain"].blueprint_nodes == ()

    def test_multiple_node_ids_on_one_line(self, tmp_path):
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
/-- Declaration with multiple links.

Blueprint: topic.alpha, topic.beta, topic.gamma
-/
def multi : Nat := 0
""".strip() + "\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        assert idx.declarations["multi"].blueprint_nodes == (
            "topic.alpha",
            "topic.beta",
            "topic.gamma",
        )

    def test_inline_module_blueprint_colon(self, tmp_path):
        """`## Blueprint: foo.bar` (inline colon form) works too."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
/-!
# Module

## Blueprint: topic.inline
-/

def x : Nat := 0
""".strip() + "\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        assert idx.declarations["x"].blueprint_nodes == ("topic.inline",)

    def test_module_blueprint_section_terminates_at_next_heading(self, tmp_path):
        """A subsequent `## Other` heading ends the Blueprint section so
        unrelated text isn't accidentally scooped up."""
        lean_root = tmp_path / "lean"
        lean_file = lean_root / "Example.lean"
        lean_file.parent.mkdir(parents=True)
        lean_file.write_text(
            """
/-!
# Module

## Blueprint

`topic.kept`

## See also

We discuss `topic.notkept` here.
-/

def x : Nat := 0
""".strip() + "\n",
            encoding="utf-8",
        )
        idx = index_lean_project(lean_root)
        assert idx.declarations["x"].blueprint_nodes == ("topic.kept",)


def test_anonymous_instance_is_not_indexed(tmp_path):
    """`noncomputable instance : T := ...` (no name) used to index as
    an empty-name declaration, producing qualified names ending in `.`
    and confusing downstream cross-checks."""
    lean_root = tmp_path / "lean"
    lean_file = lean_root / "Example.lean"
    lean_file.parent.mkdir(parents=True)
    lean_file.write_text(
        "namespace Foo\n"
        "noncomputable instance : Nat := 0\n"
        "noncomputable instance namedInst : Nat := 1\n"
        "end Foo\n",
        encoding="utf-8",
    )
    idx = index_lean_project(lean_root)
    assert "Foo.namedInst" in idx.declarations
    # No empty-named entries.
    assert not any(q.endswith(".") for q in idx.declarations)
    assert "" not in idx.declarations


def test_comment_block_text_is_not_indexed_as_declaration(tmp_path):
    """Words like 'structure under convolution' inside a `/-! ... -/`
    or `/-- ... -/` block should never be picked up as a `structure
    under` declaration."""
    lean_root = tmp_path / "lean"
    lean_file = lean_root / "Example.lean"
    lean_file.parent.mkdir(parents=True)
    lean_file.write_text(
        "/-!\n"
        "# Group structure under convolution\n"
        "\n"
        "There is a group structure under convolution.\n"
        "Some commentary about def myConcept and theorem myTheorem.\n"
        "-/\n"
        "\n"
        "namespace Real\n"
        "def actualDecl : Nat := 0\n"
        "end Real\n",
        encoding="utf-8",
    )
    idx = index_lean_project(lean_root)
    assert "Real.actualDecl" in idx.declarations
    assert "under" not in idx.declarations
    assert "myConcept" not in idx.declarations
    assert "myTheorem" not in idx.declarations


def test_multiline_doc_comment_does_not_create_spurious_decls(tmp_path):
    """`/-- ... -/` block comments are also skipped."""
    lean_root = tmp_path / "lean"
    lean_file = lean_root / "Example.lean"
    lean_file.parent.mkdir(parents=True)
    lean_file.write_text(
        "/-- A multi-line docstring that mentions\n"
        "def someProse : Nat := ...\n"
        "as an example, but is just prose.\n"
        "-/\n"
        "def real : Nat := 0\n",
        encoding="utf-8",
    )
    idx = index_lean_project(lean_root)
    assert "real" in idx.declarations
    assert "someProse" not in idx.declarations
