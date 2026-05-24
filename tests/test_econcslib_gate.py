import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

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
    assert result.artifacts["graph_topics_hierarchy.json"] == site_dir / "graph_topics_hierarchy.json"
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


def test_econcslib_gate_fails_when_lean_refs_are_unresolved_in_published_site(tmp_path):
    from tools.knowledge.econcslib_gate import GateFailure, run_gate

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo_with_lean(repo)
    site_dir = tmp_path / "site"

    with pytest.raises(GateFailure, match="unresolved Lean declarations"):
        run_gate(repo_path=repo, site_dir=site_dir, render_mode="none")


def test_econcslib_gate_can_explicitly_allow_unresolved_lean_refs(tmp_path):
    from tools.knowledge.econcslib_gate import run_gate

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo_with_lean(repo)

    result = run_gate(
        repo_path=repo,
        site_dir=tmp_path / "site",
        render_mode="none",
        allow_unresolved_lean_refs=True,
    )

    assert result.error_count == 0


def test_econcslib_gate_passes_when_lean_refs_have_source_urls(tmp_path):
    from tools.knowledge.econcslib_gate import run_gate

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo_with_lean(repo, configured=True)
    site_dir = tmp_path / "site"

    result = run_gate(repo_path=repo, site_dir=site_dir, render_mode="none")

    assert result.error_count == 0
    payload = (site_dir / "node_payloads" / "analysis_limit_unique.json").read_text()
    assert "https://example.test/fake/blob/" in payload
    assert "Analysis/Limit.lean#L" in payload


def _write_fake_econcslib_repo_with_lean(repo: Path, *, configured: bool = False) -> None:
    node_dir = repo / "docs" / "knowledge" / "nodes" / "analysis"
    node_dir.mkdir(parents=True)
    lean_file = repo / "Analysis" / "Limit.lean"
    lean_file.parent.mkdir(parents=True)
    lean_file.write_text(
        textwrap.dedent(
            """
            namespace Analysis

            theorem limit_unique : True := by
              trivial

            end Analysis
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    repository = "fake_lean_repo"
    declaration = "limit_unique"
    if configured:
        repository = "core"
        declaration = "Analysis.limit_unique"
        config_text = textwrap.dedent(
            """
            site:
              title: Fake EconCSLib Blueprint
            lean:
              default_repository: core
              repositories:
                - id: core
                  title: Fake Lean Repo
                  local_path: ../..
                  web_url: https://example.test/fake
                  source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
                  revision: auto
            """
        ).rstrip()
    else:
        config_text = textwrap.dedent(
            """
            site:
              title: Fake EconCSLib Blueprint
            """
        ).strip()
    (repo / "docs" / "knowledge" / "mdblueprint.yml").write_text(
        config_text,
        encoding="utf-8",
    )
    body = textwrap.dedent(
        rf"""
        ---
        id: analysis.limit_unique
        title: Limit Is Unique
        kind: theorem
        status: admitted
        uses: []
        lean:
          repository: {repository}
          modules:
            - Analysis.Limit
          declarations:
            - {declaration}
        tags:
          - analysis
        ---

        # Limit Is Unique

        If $\lim x_n = x$, the limit is unique.
        """
    ).strip()
    (node_dir / "limit.md").write_text(body, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# _checkout_repo (lines 54-66)
# ---------------------------------------------------------------------------


def _make_minimal_git_repo(path: Path) -> None:
    """Create a minimal git repo with a single commit at `path`."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, check=True)
    (path / "readme.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_checkout_repo_removes_stale_checkout_and_clones_fresh(tmp_path):
    """_checkout_repo removes a pre-existing checkout directory before re-cloning."""
    from tools.knowledge.econcslib_gate import _checkout_repo

    src = tmp_path / "src"
    _make_minimal_git_repo(src)

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    stale = work_dir / "EconCSLib"
    stale.mkdir()
    (stale / "stale.txt").write_text("old", encoding="utf-8")

    result = _checkout_repo(repo_url=str(src), ref="main", work_dir=work_dir)

    assert result.exists()
    assert not (result / "stale.txt").exists()


def test_checkout_repo_falls_back_when_branch_clone_fails(tmp_path, monkeypatch):
    """_checkout_repo falls back to a default clone + fetch/checkout when branch clone fails."""
    from tools.knowledge.econcslib_gate import _checkout_repo

    src = tmp_path / "src"
    _make_minimal_git_repo(src)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    real_run = subprocess.run
    call_count = {"n": 0}

    def fake_run(cmd, **kwargs):
        call_count["n"] += 1
        # First call is the branch clone — simulate failure.
        if call_count["n"] == 1 and "--branch" in cmd:
            raise subprocess.CalledProcessError(128, cmd)
        # Second call is the default clone — remap the fake URL to our local src.
        if "clone" in cmd and "--branch" not in cmd:
            cmd = [str(src) if c == "nonexistent://fake" else c for c in cmd]
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Stub _run_git so fetch/checkout don't need a real remote.
    with patch("tools.knowledge.econcslib_gate._run_git", return_value=""):
        result = _checkout_repo(
            repo_url="nonexistent://fake",
            ref="some-branch",
            work_dir=work_dir,
        )

    assert result.exists()


# ---------------------------------------------------------------------------
# _source_ref (lines 72-73, 75)
# ---------------------------------------------------------------------------


def test_source_ref_returns_requested_ref_when_git_fails(tmp_path, monkeypatch):
    """_source_ref returns requested_ref when rev-parse raises CalledProcessError."""
    from tools.knowledge.econcslib_gate import _source_ref

    monkeypatch.setattr(
        "tools.knowledge.econcslib_gate._run_git",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(128, "git")),
    )

    assert _source_ref(tmp_path, "mybranch") == "mybranch"


def test_source_ref_returns_unknown_when_git_fails_and_no_requested_ref(tmp_path, monkeypatch):
    """_source_ref returns 'unknown' when git fails and requested_ref is None."""
    from tools.knowledge.econcslib_gate import _source_ref

    monkeypatch.setattr(
        "tools.knowledge.econcslib_gate._run_git",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(128, "git")),
    )

    assert _source_ref(tmp_path, None) == "unknown"


def test_source_ref_returns_detached_when_head_is_HEAD_and_no_ref(tmp_path, monkeypatch):
    """_source_ref returns 'detached' when HEAD is detached and no requested_ref is given."""
    from tools.knowledge.econcslib_gate import _source_ref

    monkeypatch.setattr("tools.knowledge.econcslib_gate._run_git", lambda *a, **kw: "HEAD")

    assert _source_ref(tmp_path, None) == "detached"


def test_source_ref_returns_requested_ref_when_head_is_HEAD(tmp_path, monkeypatch):
    """_source_ref returns requested_ref when HEAD is detached and requested_ref is given."""
    from tools.knowledge.econcslib_gate import _source_ref

    monkeypatch.setattr("tools.knowledge.econcslib_gate._run_git", lambda *a, **kw: "HEAD")

    assert _source_ref(tmp_path, "v1.2.3") == "v1.2.3"


# ---------------------------------------------------------------------------
# _source_commit (lines 82-83)
# ---------------------------------------------------------------------------


def test_source_commit_returns_unknown_when_git_fails(tmp_path, monkeypatch):
    """_source_commit returns 'unknown' when rev-parse raises CalledProcessError."""
    from tools.knowledge.econcslib_gate import _source_commit

    monkeypatch.setattr(
        "tools.knowledge.econcslib_gate._run_git",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(128, "git")),
    )

    assert _source_commit(tmp_path) == "unknown"


# ---------------------------------------------------------------------------
# verify_graph_artifacts (line 109)
# ---------------------------------------------------------------------------


def test_verify_graph_artifacts_raises_when_artifacts_missing(tmp_path):
    """verify_graph_artifacts raises GateFailure when expected files are absent."""
    from tools.knowledge.econcslib_gate import GateFailure, verify_graph_artifacts

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    with pytest.raises(GateFailure, match="missing generated graph artifact"):
        verify_graph_artifacts(site_dir)


# ---------------------------------------------------------------------------
# verify_resolved_lean_links (lines 118, 123-124, 138)
# ---------------------------------------------------------------------------


def test_verify_resolved_lean_links_is_noop_when_payloads_dir_missing(tmp_path):
    """verify_resolved_lean_links returns silently when node_payloads dir does not exist."""
    from tools.knowledge.econcslib_gate import verify_resolved_lean_links

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    verify_resolved_lean_links(site_dir)  # Must not raise.


def test_verify_resolved_lean_links_skips_unparseable_payload_files(tmp_path):
    """verify_resolved_lean_links silently skips files that are not valid JSON."""
    from tools.knowledge.econcslib_gate import verify_resolved_lean_links

    site_dir = tmp_path / "site"
    payloads = site_dir / "node_payloads"
    payloads.mkdir(parents=True)
    (payloads / "broken.json").write_text("{not valid json", encoding="utf-8")

    verify_resolved_lean_links(site_dir)  # Must not raise.


def test_verify_resolved_lean_links_truncates_long_unresolved_list(tmp_path):
    """verify_resolved_lean_links truncates the error message after 20 items."""
    from tools.knowledge.econcslib_gate import GateFailure, verify_resolved_lean_links

    site_dir = tmp_path / "site"
    payloads = site_dir / "node_payloads"
    payloads.mkdir(parents=True)

    for i in range(25):
        payload = {
            "id": f"node_{i}",
            "lean_refs": [
                {"display_name": f"Decl{i}", "status": "unresolved", "source_url": None}
            ],
        }
        (payloads / f"node_{i:03d}.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GateFailure) as exc_info:
        verify_resolved_lean_links(site_dir)

    assert "... and 5 more" in str(exc_info.value)


# ---------------------------------------------------------------------------
# smoke_render_pages fallback path (lines 146-157)
# ---------------------------------------------------------------------------


def test_smoke_render_pages_fallback_when_no_default_pages_exist(tmp_path):
    """smoke_render_pages falls back to iter_html_pages when none of the defaults exist."""
    from tools.knowledge.econcslib_gate import smoke_render_pages

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "dep_graph_document.html").write_text("", encoding="utf-8")
    (site_dir / "graph.html").write_text("", encoding="utf-8")
    node_dir = site_dir / "analysis"
    node_dir.mkdir()
    for i in range(5):
        (node_dir / f"node_{i}.html").write_text("", encoding="utf-8")

    pages = smoke_render_pages(site_dir)

    page_names = {p.name for p in pages}
    assert "dep_graph_document.html" in page_names
    assert "graph.html" in page_names
    extra = [p for p in pages if p.name not in {"dep_graph_document.html", "graph.html"}]
    assert len(extra) <= 3


def test_smoke_render_pages_fallback_excludes_index_html(tmp_path):
    """smoke_render_pages excludes index.html from the fallback node page list."""
    from tools.knowledge.econcslib_gate import smoke_render_pages

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("", encoding="utf-8")
    (site_dir / "page_a.html").write_text("", encoding="utf-8")

    pages = smoke_render_pages(site_dir)

    names = {p.name for p in pages}
    assert "index.html" not in names
    assert "page_a.html" in names


# ---------------------------------------------------------------------------
# _render_targets (lines 173-177)
# ---------------------------------------------------------------------------


def test_render_targets_returns_empty_when_mode_is_none(tmp_path):
    """_render_targets returns [] when render_mode is 'none'."""
    from tools.knowledge.econcslib_gate import _render_targets

    assert _render_targets(tmp_path / "site", render_mode="none", render_pages=[]) == []


def test_render_targets_returns_explicit_pages(tmp_path):
    """_render_targets returns the explicit render_pages list when provided."""
    from tools.knowledge.econcslib_gate import _render_targets

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    pages = _render_targets(site_dir, render_mode="smoke", render_pages=["a.html", "b.html"])

    assert pages == [site_dir / "a.html", site_dir / "b.html"]


def test_render_targets_returns_all_pages_when_mode_is_all(tmp_path):
    """_render_targets returns all HTML pages when render_mode is 'all' and no explicit pages."""
    from tools.knowledge.econcslib_gate import _render_targets
    from tools.knowledge.render_check import iter_html_pages

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "page_x.html").write_text("", encoding="utf-8")
    (site_dir / "page_y.html").write_text("", encoding="utf-8")

    pages = _render_targets(site_dir, render_mode="all", render_pages=[])

    assert set(pages) == set(iter_html_pages(site_dir))


# ---------------------------------------------------------------------------
# run_gate invalid render_mode (line 193)
# ---------------------------------------------------------------------------


def test_run_gate_raises_value_error_for_invalid_render_mode(tmp_path):
    """run_gate raises ValueError immediately for an unknown render_mode."""
    from tools.knowledge.econcslib_gate import run_gate

    with pytest.raises(ValueError, match="render_mode must be one of"):
        run_gate(repo_path=tmp_path, render_mode="bad_mode")


# ---------------------------------------------------------------------------
# _print_result (lines 237-253)
# ---------------------------------------------------------------------------


def _make_gate_result(site_dir: Path, render_pages=None, artifacts=None):
    """Build a minimal GateResult for _print_result tests."""
    from tools.knowledge.econcslib_gate import GateResult

    if artifacts is None:
        artifacts = {
            "graph.json": site_dir / "graph.json",
            "topic_subgraphs": [site_dir / "s1.json", site_dir / "s2.json"],
        }

    return GateResult(
        source_path=site_dir.parent / "repo",
        source_ref="main",
        source_commit="abc123",
        site_dir=site_dir,
        error_count=0,
        warning_count=1,
        render_pages=render_pages or [],
        artifacts=artifacts,
    )


def test_print_result_outputs_key_fields(tmp_path, capsys):
    """_print_result prints source path, ref, commit, site dir, and diagnostics."""
    from tools.knowledge.econcslib_gate import _print_result

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    result = _make_gate_result(site_dir)
    _print_result(result)

    out = capsys.readouterr().out
    assert "EconCSLib source:" in out
    assert "EconCSLib ref:" in out
    assert "EconCSLib commit:" in out
    assert "Generated site:" in out
    assert "0 error(s)" in out


def test_print_result_shows_no_render_pages_message(tmp_path, capsys):
    """_print_result prints 'none' when render_pages is empty."""
    from tools.knowledge.econcslib_gate import _print_result

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    result = _make_gate_result(site_dir, render_pages=[])
    _print_result(result)

    out = capsys.readouterr().out
    assert "Render-check pages: none" in out


def test_print_result_lists_render_pages(tmp_path, capsys):
    """_print_result lists each render page relative to site_dir."""
    from tools.knowledge.econcslib_gate import GateResult, _print_result

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    page = site_dir / "analysis" / "node.html"
    page.parent.mkdir()
    page.write_text("", encoding="utf-8")

    result = GateResult(
        source_path=tmp_path / "repo",
        source_ref="main",
        source_commit="abc123",
        site_dir=site_dir,
        error_count=0,
        warning_count=0,
        render_pages=[page],
        artifacts={},
    )
    _print_result(result)

    out = capsys.readouterr().out
    assert "analysis/node.html" in out


def test_print_result_shows_list_artifact_count(tmp_path, capsys):
    """_print_result shows file count for list-valued artifacts."""
    from tools.knowledge.econcslib_gate import GateResult, _print_result

    site_dir = tmp_path / "site"
    site_dir.mkdir()

    result = GateResult(
        source_path=tmp_path / "repo",
        source_ref="main",
        source_commit="abc123",
        site_dir=site_dir,
        error_count=0,
        warning_count=0,
        render_pages=[],
        artifacts={
            "graph.json": site_dir / "graph.json",
            "topic_subgraphs": [site_dir / "a.json", site_dir / "b.json"],
        },
    )
    _print_result(result)

    out = capsys.readouterr().out
    assert "2 file(s)" in out


# ---------------------------------------------------------------------------
# main() / CLI (lines 257-288)
# ---------------------------------------------------------------------------


def test_main_calls_run_gate_and_prints_result(tmp_path):
    """main() parses argv and passes all args to run_gate."""
    from tools.knowledge.econcslib_gate import main

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo)
    site_dir = tmp_path / "site"

    main(
        [
            "--repo-path",
            str(repo),
            "--site-dir",
            str(site_dir),
            "--render-mode",
            "none",
        ]
    )

    assert site_dir.exists()


def test_main_exits_with_1_on_gate_failure(tmp_path):
    """main() writes error to stderr and exits with code 1 on GateFailure."""
    from tools.knowledge.econcslib_gate import main

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo, valid=False)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "--repo-path",
                str(repo),
                "--site-dir",
                str(tmp_path / "site"),
                "--render-mode",
                "none",
            ]
        )

    assert exc_info.value.code == 1


def test_main_passes_allow_unresolved_lean_refs_flag(tmp_path):
    """main() forwards --allow-unresolved-lean-refs to run_gate."""
    from tools.knowledge.econcslib_gate import main

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo_with_lean(repo)

    main(
        [
            "--repo-path",
            str(repo),
            "--site-dir",
            str(tmp_path / "site"),
            "--render-mode",
            "none",
            "--allow-unresolved-lean-refs",
        ]
    )  # Must not raise.


def test_main_passes_render_page_args_to_run_gate(tmp_path):
    """main() collects repeatable --render-page args and passes them to run_gate."""
    from tools.knowledge.econcslib_gate import GateResult, main

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo)
    site_dir = tmp_path / "site"
    site_dir.mkdir()

    with patch("tools.knowledge.econcslib_gate.run_gate") as mock_rg:
        mock_rg.return_value = GateResult(
            source_path=repo,
            source_ref="main",
            source_commit="abc",
            site_dir=site_dir,
            error_count=0,
            warning_count=0,
            render_pages=[],
            artifacts={},
        )
        main(
            [
                "--repo-path",
                str(repo),
                "--render-mode",
                "smoke",
                "--render-page",
                "graph.html",
                "--render-page",
                "dep_graph_document.html",
            ]
        )
        _, kwargs = mock_rg.call_args
        assert kwargs["render_pages"] == ["graph.html", "dep_graph_document.html"]


def test_main_default_argv_uses_sys_argv(tmp_path, monkeypatch):
    """main() reads sys.argv[1:] when argv is None."""
    import sys

    from tools.knowledge.econcslib_gate import main

    repo = tmp_path / "repo"
    _write_fake_econcslib_repo(repo)
    site_dir = tmp_path / "site"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "econcslib_gate",
            "--repo-path",
            str(repo),
            "--site-dir",
            str(site_dir),
            "--render-mode",
            "none",
        ],
    )
    main()  # argv=None — should read from sys.argv[1:]
    assert site_dir.exists()
