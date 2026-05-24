import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

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


def test_project_config_uses_graph_display_defaults(tmp_path):
    from tools.knowledge.config import load_project_config

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            """
            site:
              title: Graph Defaults Blueprint
            """
        ).strip(),
        encoding="utf-8",
    )

    config = load_project_config(knowledge_root)

    assert config.graph.max_visible_nodes == 120
    assert config.graph.max_expand_nodes == 80
    assert config.graph.proof_plans == "selected-only"


def test_project_config_parses_graph_display_limits(tmp_path):
    from tools.knowledge.config import load_project_config

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            """
            site:
              title: Graph Limits Blueprint
            graph:
              max_visible_nodes: 40
              max_expand_nodes: 25
              proof_plans: hidden
            """
        ).strip(),
        encoding="utf-8",
    )

    config = load_project_config(knowledge_root)

    assert config.graph.max_visible_nodes == 40
    assert config.graph.max_expand_nodes == 25
    assert config.graph.proof_plans == "hidden"


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


def test_katex_options_do_not_override_builtin_macros_that_can_recurse():
    from tools.knowledge.config import MathConfig, katex_auto_render_options

    options = katex_auto_render_options(MathConfig(
        macros={
            "notin": r"\notin",
            "ldots": r"\dots",
            "ast": r"\ast",
            "R": r"\mathbb{R}",
        },
        inline_delimiters=[(r"\(", r"\)")],
        display_delimiters=[(r"\[", r"\]")],
    ))

    assert options["macros"] == {r"\R": r"\mathbb{R}"}


def _init_git_repo(path: Path) -> str:
    path.mkdir(parents=True)
    (path / "Example.lean").write_text("theorem Example : True := True.intro\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "Example.lean"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def test_project_config_parses_lean_repository_and_auto_revision(tmp_path):
    from tools.knowledge.config import load_project_config

    lean_root = tmp_path / "lean_project"
    revision = _init_git_repo(lean_root)
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Lean Linked Blueprint
            lean:
              default_repository: main
              repositories:
                - id: main
                  title: Example Lean Library
                  local_path: {lean_root}
                  web_url: https://example.test/org/repo
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: auto
            """
        ).strip(),
        encoding="utf-8",
    )

    config = load_project_config(knowledge_root)
    repo = config.lean.repositories["main"]

    assert config.lean.default_repository == "main"
    assert repo.title == "Example Lean Library"
    assert repo.local_path == lean_root
    assert repo.web_url == "https://example.test/org/repo"
    assert repo.revision == revision
    assert len(repo.revision) == 40


def test_lean_repository_local_path_must_exist(tmp_path):
    from tools.knowledge.config import load_project_config

    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    missing = tmp_path / "missing_lean"
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Missing Lean Blueprint
            lean:
              repositories:
                - id: main
                  title: Missing Lean
                  local_path: {missing}
                  web_url: https://example.test/org/repo
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: fixed
            """
        ).strip(),
        encoding="utf-8",
    )

    try:
        load_project_config(knowledge_root)
    except ValueError as exc:
        assert "lean.repositories[0].local_path" in str(exc)
        assert str(missing) in str(exc)
    else:
        raise AssertionError("expected missing local_path to fail")


def test_lean_repository_reports_missing_required_fields(tmp_path):
    from tools.knowledge.config import load_project_config

    lean_root = tmp_path / "lean_project"
    _init_git_repo(lean_root)
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Incomplete Lean Blueprint
            lean:
              repositories:
                - id: main
                  title: Incomplete Lean
                  local_path: {lean_root}
                  revision: auto
            """
        ).strip(),
        encoding="utf-8",
    )

    try:
        load_project_config(knowledge_root)
    except ValueError as exc:
        assert "lean.repositories[0].web_url" in str(exc)
    else:
        raise AssertionError("expected missing web_url to fail")


def test_load_project_config_reads_lint_fuzzy_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Lint Threshold Test\n"
        "lint:\n  fuzzy_threshold: 0.88\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.88


def test_load_project_config_uses_default_lint_threshold_when_section_missing(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Default Lint Threshold\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.92


def test_load_project_config_rejects_non_numeric_lint_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Bad Lint Threshold\n"
        "lint:\n  fuzzy_threshold: nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fuzzy_threshold"):
        load_project_config(tmp_path)


def test_load_project_config_rejects_lint_threshold_out_of_range(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Out of Range\n"
        "lint:\n  fuzzy_threshold: 1.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fuzzy_threshold"):
        load_project_config(tmp_path)


def test_load_project_config_reads_semantic_candidate_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Semantic Threshold Test\n"
        "lint:\n"
        "  fuzzy_threshold: 0.91\n"
        "  semantic_candidate_threshold: 0.65\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.91
    assert cfg.lint.semantic_candidate_threshold == 0.65


def test_load_project_config_uses_default_semantic_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Default Semantic Threshold\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.semantic_candidate_threshold == 0.75


def test_load_project_config_rejects_bad_semantic_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Bad Semantic Threshold\n"
        "lint:\n  semantic_candidate_threshold: 2.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="semantic_candidate_threshold"):
        load_project_config(tmp_path)
