import subprocess
import textwrap
from pathlib import Path

import pytest


def _write_fake_econcslib_repo(repo: Path, *, valid: bool = True) -> None:
    node_dir = repo / "docs" / "knowledge" / "nodes" / "analysis"
    node_dir.mkdir(parents=True)
    (repo / "docs" / "knowledge" / "mdblueprint.yml").write_text(
        textwrap.dedent(
            """
            site:
              title: Fake EconCSLib Blueprint
            """
        ).strip(),
        encoding="utf-8",
    )
    if valid:
        body = textwrap.dedent(
            r"""
            ---
            id: analysis.limit_unique
            title: Limit Is Unique
            kind: theorem
            status: admitted
            uses: []
            tags:
              - analysis
            ---

            # Limit Is Unique

            If $\lim x_n = x$, the limit is unique.
            """
        ).strip()
    else:
        body = textwrap.dedent(
            """
            ---
            id: analysis.bad_plan
            title: Bad Plan
            kind: proof-plan
            status: admitted
            uses: []
            tags:
              - analysis
            ---

            # Bad Plan
            """
        ).strip()
    (node_dir / "limit.md").write_text(body, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)


def test_econcslib_gate_uses_current_checkout_and_verifies_graph_artifacts(tmp_path):
    from tools.knowledge.econcslib_gate import run_gate

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo)
    site_dir = tmp_path / "site"

    result = run_gate(
        repo_path=repo,
        site_dir=site_dir,
        render_mode="none",
    )

    assert result.source_path == repo.resolve()
    assert result.source_commit
    assert result.site_dir == site_dir.resolve()
    assert result.error_count == 0
    assert result.artifacts["graph_topics.json"] == site_dir / "graph_topics.json"
    assert result.artifacts["topic_subgraphs"]
    assert result.artifacts["node_payloads"]


def test_econcslib_gate_fails_when_check_reports_errors(tmp_path):
    from tools.knowledge.econcslib_gate import GateFailure, run_gate

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo, valid=False)

    with pytest.raises(GateFailure, match="check reported 2 error"):
        run_gate(repo_path=repo, site_dir=tmp_path / "site", render_mode="none")


def test_econcslib_gate_smoke_render_pages_are_bounded(tmp_path):
    from tools.knowledge.econcslib_gate import smoke_render_pages

    site_dir = tmp_path / "site"
    (site_dir / "dep_graph_document.html").parent.mkdir(parents=True)
    (site_dir / "dep_graph_document.html").write_text("", encoding="utf-8")
    (site_dir / "graph.html").write_text("", encoding="utf-8")
    (site_dir / "approachability").mkdir()
    (site_dir / "approachability" / "approachability_blackwell_b_set_approachability.html").write_text(
        "",
        encoding="utf-8",
    )
    for index in range(50):
        page = site_dir / "bulk" / f"page_{index}.html"
        page.parent.mkdir(exist_ok=True)
        page.write_text("", encoding="utf-8")

    pages = smoke_render_pages(site_dir)

    assert [page.relative_to(site_dir).as_posix() for page in pages] == [
        "approachability/approachability_blackwell_b_set_approachability.html",
        "dep_graph_document.html",
        "graph.html",
    ]
