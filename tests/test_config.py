import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.publish import publish


def _write_minimal_knowledge_root(knowledge_root: Path) -> None:
    node_dir = knowledge_root / "nodes" / "algebra"
    node_dir.mkdir(parents=True)
    (node_dir / "group.md").write_text(
        textwrap.dedent(
            """
            ---
            id: algebra.group
            title: Group
            kind: definition
            status: admitted
            uses: []
            tags:
              - algebra
            ---

            # Group

            A group is a set with an associative operation, identity, and inverses.
            """
        ).strip(),
        encoding="utf-8",
    )


def test_project_config_controls_site_title_logo_and_index_h1(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    _write_minimal_knowledge_root(knowledge_root)
    config_path = tmp_path / "site.yml"
    config_path.write_text(
        textwrap.dedent(
            """
            site:
              title: Example Algebra Blueprint
              short_title: Algebra
            """
        ).strip(),
        encoding="utf-8",
    )

    publish(knowledge_root, tmp_path / "site", config_path=config_path)

    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    node_page = (tmp_path / "site" / "algebra" / "algebra_group.html").read_text(encoding="utf-8")
    assert "<h1>Example Algebra Blueprint</h1>" in index
    assert '<a class="logo" href="index.html">Algebra</a>' in index
    assert "<title>Group — Example Algebra Blueprint</title>" in node_page
    assert '<a class="logo" href="../index.html">Algebra</a>' in node_page
    assert "Knowledge Base" not in index
    assert "mdblueprint" not in index


def test_publish_without_config_uses_root_name_fallback(tmp_path):
    knowledge_root = tmp_path / "linear_algebra_project"
    _write_minimal_knowledge_root(knowledge_root)

    publish(knowledge_root, tmp_path / "site")

    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    node_page = (tmp_path / "site" / "algebra" / "algebra_group.html").read_text(encoding="utf-8")
    assert "<h1>Linear Algebra Project</h1>" in index
    assert "<title>Group — Linear Algebra Project</title>" in node_page
    assert "Knowledge Base" not in index
    assert "mdblueprint" not in index


def test_cli_accepts_config_path(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    _write_minimal_knowledge_root(knowledge_root)
    output_dir = tmp_path / "site"
    config_path = tmp_path / "custom-site.yml"
    config_path.write_text(
        textwrap.dedent(
            """
            site:
              title: CLI Blueprint
              short_title: CLI
            """
        ).strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.publish",
            str(knowledge_root),
            str(output_dir),
            "--config",
            str(config_path),
        ],
        cwd=Path(__file__).parent.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    index = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "<h1>CLI Blueprint</h1>" in index
    assert '<a class="logo" href="index.html">CLI</a>' in index
