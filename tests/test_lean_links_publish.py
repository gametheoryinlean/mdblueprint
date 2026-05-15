import textwrap
from pathlib import Path

from tools.knowledge.publish import publish


def _write_lean_file(lean_root: Path) -> None:
    lean_file = lean_root / "Example" / "Basic.lean"
    lean_file.parent.mkdir(parents=True, exist_ok=True)
    lean_file.write_text("theorem Example.ok : True := True.intro\n", encoding="utf-8")


def _write_config(knowledge_root: Path, lean_root: Path) -> None:
    knowledge_root.mkdir(parents=True, exist_ok=True)
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Lean Link Blueprint
            lean:
              default_repository: main
              repositories:
                - id: main
                  title: Example Lean Library
                  local_path: {lean_root}
                  web_url: https://example.test/org/repo
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: abc123def456
            """
        ).strip(),
        encoding="utf-8",
    )


def _write_node(knowledge_root: Path, *, declaration: str) -> None:
    node_dir = knowledge_root / "nodes" / "example"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "ok.md").write_text(
        textwrap.dedent(
            f"""
            ---
            id: example.ok
            title: Example OK
            kind: theorem
            status: admitted
            uses: []
            lean:
              repository: main
              modules:
                - Example.Basic
              declarations:
                - {declaration}
            verification:
              statement: accepted
              proof: accepted
            ---

            # Example OK

            This theorem links to Lean.
            """
        ).strip(),
        encoding="utf-8",
    )


def test_node_and_graph_lean_modals_link_to_configured_source_url(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text(encoding="utf-8")
    source_url = "https://example.test/org/repo/blob/abc123def456/Example/Basic.lean#L1"

    assert source_url in node_page
    assert source_url in graph_page
    assert "Example Lean Library" in node_page
    assert "Example Lean Library" in graph_page
    assert "abc123d" in node_page
    assert "abc123d" in graph_page
    assert "Example.ok" in node_page
    assert "Example.ok" in graph_page


def test_unresolved_lean_reference_is_shown_without_broken_source_link(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.missing")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text(encoding="utf-8")

    assert "Example.missing" in node_page
    assert "Example.missing" in graph_page
    assert "Unresolved" in node_page
    assert "Unresolved" in graph_page
    assert "Example.missing#L" not in node_page
    assert "Example.missing#L" not in graph_page
