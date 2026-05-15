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
    assert "MDBLUEPRINT_MATH_OPTIONS" in node_page


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


def test_project_config_parses_math_macros_delimiters_and_strictness(tmp_path):
    from tools.knowledge.config import load_project_config

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    config_path = knowledge_root / "mdblueprint.yml"
    config_path.write_text(
        textwrap.dedent(
            r"""
            site:
              title: Configured Blueprint
            math:
              macros:
                R: "\\mathbb{R}"
                Prob: "\\mathbb{P}"
              delimiters:
                inline:
                  - ["\\(", "\\)"]
                display:
                  - ["\\[", "\\]"]
              throw_on_error: true
            """
        ).strip(),
        encoding="utf-8",
    )

    config = load_project_config(knowledge_root)

    assert config.math.macros == {"R": r"\mathbb{R}", "Prob": r"\mathbb{P}"}
    assert config.math.inline_delimiters == [(r"\(", r"\)")]
    assert config.math.display_delimiters == [(r"\[", r"\]")]
    assert config.math.throw_on_error is True


def test_publish_injects_configured_math_options(tmp_path):
    knowledge_root = tmp_path / "knowledge"
    _write_minimal_knowledge_root(knowledge_root)
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            r"""
            site:
              title: Math Config Blueprint
            math:
              macros:
                R: "\\mathbb{R}"
              delimiters:
                inline:
                  - ["\\(", "\\)"]
                display:
                  - ["\\[", "\\]"]
              throw_on_error: true
            """
        ).strip(),
        encoding="utf-8",
    )

    publish(knowledge_root, tmp_path / "site")

    node_page = (tmp_path / "site" / "algebra" / "algebra_group.html").read_text(encoding="utf-8")
    assert "MDBLUEPRINT_MATH_OPTIONS" in node_page
    assert r'"\\R": "\\mathbb{R}"' in node_page
    assert '"throwOnError": true' in node_page
    assert r'"left": "\\("' in node_page
    assert r'"left": "$"' not in node_page
