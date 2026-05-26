from pathlib import Path
import subprocess
import textwrap

from tools.knowledge.lean_check import check_lean_references
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.models import LeanRef, Node
from tools.knowledge.check import check_knowledge_base

LEAN_FIXTURES = Path(__file__).parent / "fixtures" / "lean"


def _make_idx():
    return index_lean_project(LEAN_FIXTURES)


def _write_node(path: Path, *, node_id: str, lean_block: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_lean = textwrap.indent(textwrap.dedent(lean_block).strip(), "  ")
    path.write_text(
        (
            "---\n"
            f"id: {node_id}\n"
            "title: Lean Node\n"
            "kind: theorem\n"
            "status: admitted\n"
            "uses: []\n"
            "lean:\n"
            f"{normalized_lean}\n"
            "verification:\n"
            "  statement: accepted\n"
            "  proof: accepted\n"
            "---\n\n"
            "# Lean Node\n\n"
            "A node with Lean references.\n"
        ),
        encoding="utf-8",
    )


def _init_lean_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        lean_file = path / rel
        lean_file.parent.mkdir(parents=True, exist_ok=True)
        lean_file.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def _write_project_config(knowledge_root: Path, lean_root: Path, *, default_repository: str | None = "main") -> None:
    knowledge_root.mkdir(parents=True, exist_ok=True)
    default_line = f"  default_repository: {default_repository}\n" if default_repository is not None else ""
    (knowledge_root / "mdblueprint.yml").write_text(
        (
            "site:\n"
            "  title: Configured Lean Blueprint\n"
            "lean:\n"
            f"{default_line}"
            "  repositories:\n"
            "    - id: main\n"
            "      title: Example Lean Library\n"
            f"      local_path: {lean_root}\n"
            "      web_url: https://example.test/org/repo\n"
            '      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"\n'
            "      revision: auto\n"
        ),
        encoding="utf-8",
    )


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

    def test_missing_declaration_includes_suggestions(self):
        """When a similar name exists in the index, the warning should
        include a suggestion so the user can fix the typo quickly."""
        idx = _make_idx()
        # No declaration matches "IsBestResponser" exactly or as suffix,
        # but its tokens overlap heavily with the real
        # `StrategicGame.IsBestResponse` (IsBestResponser -> tokens
        # {is, best, responser} vs {is, best, response} share 2 tokens).
        node = Node(
            id="test.typo",
            title="Typo",
            kind="definition",
            status="admitted",
            lean=LeanRef(
                modules=["GameTheoryLib.StrategicGame.Basic"],
                declarations=["IsBestResponser"],
            ),
        )
        diags = check_lean_references([node], idx)
        warnings = [d for d in diags if d.level == "warning"]
        assert any("IsBestResponser" in d.message for d in warnings)
        # The token-overlap fallback should propose IsBestResponse.
        assert any(
            "suggestions:" in d.message and "IsBestResponse" in d.message
            for d in warnings
        )

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


class TestConfiguredLeanChecks:
    def test_default_repository_resolves_references(self, tmp_path):
        lean_root = tmp_path / "lean"
        _init_lean_repo(lean_root, {"Example/Basic.lean": "theorem Example.ok : True := True.intro"})
        knowledge_root = tmp_path / "knowledge"
        _write_project_config(knowledge_root, lean_root)
        _write_node(
            knowledge_root / "nodes" / "example" / "ok.md",
            node_id="example.ok",
            lean_block="""
            modules:
              - Example.Basic
            declarations:
              - Example.ok
            """,
        )

        errors = [d for d in check_knowledge_base(knowledge_root) if d.level == "error"]

        assert errors == []

    def test_missing_repository_id_is_error(self, tmp_path):
        lean_root = tmp_path / "lean"
        _init_lean_repo(lean_root, {"Example/Basic.lean": "theorem Example.ok : True := True.intro"})
        knowledge_root = tmp_path / "knowledge"
        _write_project_config(knowledge_root, lean_root)
        _write_node(
            knowledge_root / "nodes" / "example" / "bad_repo.md",
            node_id="example.bad_repo",
            lean_block="""
            repository: missing
            modules:
              - Example.Basic
            declarations:
              - Example.ok
            """,
        )

        errors = [d for d in check_knowledge_base(knowledge_root) if d.level == "error"]

        assert any("Lean repository not configured: 'missing'" in d.message for d in errors)

    def test_missing_refs_include_repository_context(self, tmp_path):
        lean_root = tmp_path / "lean"
        _init_lean_repo(lean_root, {"Example/Basic.lean": "theorem Example.ok : True := True.intro"})
        knowledge_root = tmp_path / "knowledge"
        _write_project_config(knowledge_root, lean_root)
        _write_node(
            knowledge_root / "nodes" / "example" / "missing.md",
            node_id="example.missing",
            lean_block="""
            modules:
              - Example.Missing
            declarations:
              - Example.missing
            """,
        )

        warnings = [d for d in check_knowledge_base(knowledge_root) if d.level == "warning"]

        assert any("repository 'main'" in d.message and "Example.Missing" in d.message for d in warnings)
        assert any("repository 'main'" in d.message and "Example.missing" in d.message for d in warnings)

    def test_ambiguous_partial_declaration_match_is_error(self, tmp_path):
        lean_root = tmp_path / "lean"
        _init_lean_repo(
            lean_root,
            {
                "Example/A.lean": "namespace A\n\ntheorem Foo : True := True.intro\n\nend A",
                "Example/B.lean": "namespace B\n\ntheorem Foo : True := True.intro\n\nend B",
            },
        )
        knowledge_root = tmp_path / "knowledge"
        _write_project_config(knowledge_root, lean_root)
        _write_node(
            knowledge_root / "nodes" / "example" / "ambiguous.md",
            node_id="example.ambiguous",
            lean_block="""
            modules:
              - Example.A
            declarations:
              - Foo
            """,
        )

        errors = [d for d in check_knowledge_base(knowledge_root) if d.level == "error"]

        assert any("ambiguous Lean declaration" in d.message and "A.Foo" in d.message and "B.Foo" in d.message for d in errors)

    def test_dirty_repository_state_is_reported(self, tmp_path):
        lean_root = tmp_path / "lean"
        _init_lean_repo(lean_root, {"Example/Basic.lean": "theorem Example.ok : True := True.intro"})
        (lean_root / "Scratch.lean").write_text("theorem Scratch : True := True.intro\n", encoding="utf-8")
        knowledge_root = tmp_path / "knowledge"
        _write_project_config(knowledge_root, lean_root)
        _write_node(
            knowledge_root / "nodes" / "example" / "ok.md",
            node_id="example.ok",
            lean_block="""
            modules:
              - Example.Basic
            declarations:
              - Example.ok
            """,
        )

        warnings = [d for d in check_knowledge_base(knowledge_root) if d.level == "warning"]

        assert any("repository 'main' has uncommitted or untracked files" in d.message for d in warnings)
