import json
import subprocess
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


def test_doc_url_template_renders_second_link(tmp_path):
    """A configured `doc_url_template` renders a second 'doc' link next
    to the source link in the modal."""
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
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
                  doc_url_template: "https://docs.example.test/{{module_html}}.html#{{qualified_name}}"
                  revision: abc123def456
            """
        ).strip(),
        encoding="utf-8",
    )
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")
    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )

    expected_doc = "https://docs.example.test/Example/Basic.html#Example.ok"
    assert expected_doc in node_page
    assert "lean-doc-link" in node_page
    assert graph_payload["lean_refs"][0]["doc_url"] == expected_doc


def test_doc_url_template_absent_leaves_doc_url_null(tmp_path):
    """No `doc_url_template` -> doc_url is null and no second link."""
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )
    assert graph_payload["lean_refs"][0]["doc_url"] is None


def test_unresolved_decl_shows_did_you_mean(tmp_path):
    """When `lean.declarations` lists a name that's a typo of a real
    declaration, the rendered modal should surface a 'Did you mean'
    suggestion."""
    lean_root = tmp_path / "lean"
    lean_file = lean_root / "Example" / "Basic.lean"
    lean_file.parent.mkdir(parents=True, exist_ok=True)
    lean_file.write_text(
        "theorem Example.bestResponse (n : Nat) : True := True.intro\n",
        encoding="utf-8",
    )
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    # Asks for a token-overlap typo
    _write_node(knowledge_root, declaration="Example.bestResponser")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )
    assert "Did you mean" in node_page
    assert "Example.bestResponse" in node_page
    assert graph_payload["lean_refs"][0]["status"] == "unresolved"
    assert "Example.bestResponse" in graph_payload["lean_refs"][0]["suggestions"]


def test_kind_signature_and_docstring_rendered(tmp_path):
    """Resolved Lean declarations should surface kind, signature, and
    docstring in the rendered modal."""
    lean_root = tmp_path / "lean"
    lean_file = lean_root / "Example" / "Basic.lean"
    lean_file.parent.mkdir(parents=True, exist_ok=True)
    lean_file.write_text(
        textwrap.dedent(
            """
            /-- A trivially true theorem used in tests. -/
            theorem Example.ok (n : Nat) :
                n + 0 = n := by
              simp
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )

    # Kind badge
    assert ">theorem<" in node_page
    # Docstring rendered
    assert "trivially true theorem" in node_page
    # Signature snippet rendered
    assert "n + 0 = n" in node_page

    # JSON payload exposes the same fields
    assert graph_payload["lean_refs"][0]["kind"] == "theorem"
    assert "trivially true" in graph_payload["lean_refs"][0]["docstring"]
    assert "n + 0 = n" in graph_payload["lean_refs"][0]["signature"]


def test_module_references_link_to_file_at_line_one(tmp_path):
    """A `lean.modules` entry should render as a clickable link to line 1
    of the file backing that module."""
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    module_link = (
        "https://example.test/org/repo/blob/abc123def456/Example/Basic.lean#L1"
    )
    # The module name appears inside an anchor tag pointing at line 1.
    assert f'href="{module_link}"' in node_page
    assert "<code>Example.Basic</code>" in node_page


def test_unresolved_module_reference_is_marked_without_link(tmp_path):
    """A module name that isn't in the repository surfaces as Unresolved
    and is rendered without a broken anchor."""
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)

    node_dir = knowledge_root / "nodes" / "example"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "ok.md").write_text(
        textwrap.dedent(
            """
            ---
            id: example.ok
            title: Example OK
            kind: theorem
            status: admitted
            uses: []
            lean:
              repository: main
              modules:
                - Example.NotAModule
              declarations:
                - Example.ok
            verification:
              statement: accepted
              proof: accepted
            ---

            # Example OK
            """
        ).strip(),
        encoding="utf-8",
    )

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    assert "Example.NotAModule" in node_page
    # Unresolved module should not produce an anchor with NotAModule
    assert 'href="https://example.test/org/repo' not in node_page or \
           "NotAModule.lean" not in node_page
    assert "Unresolved" in node_page


def test_node_and_graph_lean_modals_link_to_configured_source_url(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )
    graph_payload_json = json.dumps(graph_payload)
    source_url = "https://example.test/org/repo/blob/abc123def456/Example/Basic.lean#L1"

    assert source_url in node_page
    assert source_url in graph_payload_json
    assert "Example Lean Library" in node_page
    assert "Example Lean Library" in graph_payload_json
    assert "abc123d" in node_page
    assert "abc123d" in graph_payload_json
    assert "Example.ok" in node_page
    assert "Example.ok" in graph_payload_json


def test_unresolved_lean_reference_is_shown_without_broken_source_link(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean_file(lean_root)
    knowledge_root = tmp_path / "knowledge"
    _write_config(knowledge_root, lean_root)
    _write_node(knowledge_root, declaration="Example.missing")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )
    graph_payload_json = json.dumps(graph_payload)

    assert "Example.missing" in node_page
    assert "Example.missing" in graph_payload_json
    assert "Unresolved" in node_page
    assert '"status": "unresolved"' in graph_payload_json
    assert "Example.missing#L" not in node_page
    assert "Example.missing#L" not in graph_payload_json


def test_private_github_repo_links_use_plain_urls_and_auto_revision(tmp_path):
    lean_root = tmp_path / "private-lean"
    _write_lean_file(lean_root)
    subprocess.run(["git", "init"], cwd=lean_root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=lean_root, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "Initial Lean library",
        ],
        cwd=lean_root,
        check=True,
        capture_output=True,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lean_root, text=True).strip()

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Private Lean Blueprint
            lean:
              default_repository: main
              repositories:
                - id: main
                  title: Private Lean Library
                  local_path: {lean_root}
                  web_url: https://github.com/private-org/private-lean
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: auto
            """
        ).strip(),
        encoding="utf-8",
    )
    _write_node(knowledge_root, declaration="Example.ok")

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "example" / "example_ok.html").read_text(encoding="utf-8")
    graph_payload = json.loads(
        (tmp_path / "site" / "node_payloads" / "example_ok.json").read_text(encoding="utf-8")
    )
    graph_payload_json = json.dumps(graph_payload)
    source_url = f"https://github.com/private-org/private-lean/blob/{revision}/Example/Basic.lean#L1"
    generated = node_page + graph_payload_json

    assert source_url in generated
    assert "token" not in generated.lower()
    assert "secret" not in generated.lower()
    assert "ghp_" not in generated
