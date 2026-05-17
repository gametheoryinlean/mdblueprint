"""Integration gate for publishing the real EconCSLib knowledge base."""
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.knowledge.check import check_knowledge_base
from tools.knowledge.publish import publish
from tools.knowledge.render_check import iter_html_pages, run_browser_render_check
from tools.knowledge.validator import Diagnostic


DEFAULT_REPO_URL = "https://github.com/" "game" "theoryinlean" "/EconCSLib.git"
DEFAULT_REF = "main"
DEFAULT_SMOKE_PAGES = (
    "approachability/approachability_blackwell_b_set_approachability.html",
    "strategic_game/strategic_game_epsilon_perfect_equilibrium.html",
    "strategic_game/strategic_game_mixed_extension.html",
    "zero_sum/zero_sum_von_neumann_minimax.html",
    "zerosum/zerosum_minimax_from_loomis.html",
    "dep_graph_document.html",
    "graph.html",
)


class GateFailure(RuntimeError):
    """Raised when the real-library gate finds a blocking problem."""


@dataclass(frozen=True)
class GateResult:
    source_path: Path
    source_ref: str
    source_commit: str
    site_dir: Path
    error_count: int
    warning_count: int
    render_pages: list[Path]
    artifacts: dict[str, Path | list[Path]]


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.STDOUT).strip()


def _checkout_repo(*, repo_url: str, ref: str, work_dir: Path) -> Path:
    checkout = work_dir / "EconCSLib"
    if checkout.exists():
        shutil.rmtree(checkout)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, repo_url, str(checkout)],
            check=True,
        )
    except subprocess.CalledProcessError:
        subprocess.run(["git", "clone", "--depth", "1", repo_url, str(checkout)], check=True)
        _run_git(["fetch", "--depth", "1", "origin", ref], cwd=checkout)
        _run_git(["checkout", "FETCH_HEAD"], cwd=checkout)
    return checkout.resolve()


def _source_ref(repo: Path, requested_ref: str | None) -> str:
    try:
        ref = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    except subprocess.CalledProcessError:
        return requested_ref or "unknown"
    if ref == "HEAD":
        return requested_ref or "detached"
    return ref


def _source_commit(repo: Path) -> str:
    try:
        return _run_git(["rev-parse", "HEAD"], cwd=repo)
    except subprocess.CalledProcessError:
        return "unknown"


def _artifact_paths(site_dir: Path) -> dict[str, Path | list[Path]]:
    topic_subgraphs = sorted((site_dir / "subgraphs" / "topics").glob("*.json"))
    node_payloads = sorted((site_dir / "node_payloads").glob("*.json"))
    return {
        "graph.json": site_dir / "graph.json",
        "graph_topics.json": site_dir / "graph_topics.json",
        "dep_graph_document.html": site_dir / "dep_graph_document.html",
        "graph.html": site_dir / "graph.html",
        "topic_subgraphs": topic_subgraphs,
        "node_payloads": node_payloads,
    }


def verify_graph_artifacts(site_dir: Path) -> dict[str, Path | list[Path]]:
    artifacts = _artifact_paths(site_dir)
    missing = [
        name
        for name, value in artifacts.items()
        if (isinstance(value, Path) and not value.exists())
        or (isinstance(value, list) and not value)
    ]
    if missing:
        raise GateFailure(f"missing generated graph artifact(s): {', '.join(missing)}")
    return artifacts


def verify_resolved_lean_links(site_dir: Path) -> None:
    import json
    payloads_dir = site_dir / "node_payloads"
    if not payloads_dir.exists():
        return
    unresolved: list[tuple[str, str, str]] = []
    for payload_file in sorted(payloads_dir.glob("*.json")):
        try:
            payload = json.loads(payload_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        lean_refs = payload.get("lean_refs", [])
        for ref in lean_refs:
            status = ref.get("status", "unknown")
            if status in ("raw", "unresolved"):
                node_id = payload.get("id", payload_file.stem)
                decl_name = ref.get("display_name") or ref.get("name", "?")
                unresolved.append((node_id, decl_name, status))
    if unresolved:
        lines = ["unresolved Lean declarations found in generated site:"]
        for node_id, decl_name, status in unresolved[:20]:
            lines.append(f"  {node_id}: {decl_name} ({status})")
        if len(unresolved) > 20:
            lines.append(f"  ... and {len(unresolved) - 20} more")
        raise GateFailure("\n".join(lines))


def smoke_render_pages(site_dir: Path) -> list[Path]:
    selected = [site_dir / page for page in DEFAULT_SMOKE_PAGES if (site_dir / page).exists()]
    if selected:
        return selected
    pages = iter_html_pages(site_dir)
    graph_pages = [
        page
        for page in (site_dir / "dep_graph_document.html", site_dir / "graph.html")
        if page.exists()
    ]
    first_node_pages = [
        page
        for page in pages
        if page.name not in {"index.html", "dep_graph_document.html", "graph.html"}
    ][:3]
    return sorted({*graph_pages, *first_node_pages})


def _diagnostic_counts(diags: list[Diagnostic]) -> tuple[int, int]:
    errors = sum(1 for diag in diags if diag.level == "error")
    warnings = sum(1 for diag in diags if diag.level == "warning")
    return errors, warnings


def _diagnostic_report(diags: list[Diagnostic]) -> str:
    return "\n".join(str(diag) for diag in sorted(diags, key=lambda d: (d.level, str(d.file_path or ""))))


def _render_targets(site_dir: Path, *, render_mode: str, render_pages: list[str]) -> list[Path]:
    if render_mode == "none":
        return []
    if render_pages:
        return [site_dir / page for page in render_pages]
    if render_mode == "all":
        return iter_html_pages(site_dir)
    return smoke_render_pages(site_dir)


def run_gate(
    *,
    repo_path: Path | None = None,
    repo_url: str = DEFAULT_REPO_URL,
    ref: str = DEFAULT_REF,
    work_dir: Path | None = None,
    site_dir: Path | None = None,
    render_mode: str = "smoke",
    render_pages: list[str] | None = None,
    timeout_ms: int = 30_000,
) -> GateResult:
    if render_mode not in {"smoke", "all", "none"}:
        raise ValueError("render_mode must be one of: smoke, all, none")

    with tempfile.TemporaryDirectory(prefix="mdblueprint-econcslib-gate-") as tmp:
        tmp_dir = Path(tmp)
        checkout_root = work_dir or tmp_dir
        source_path = repo_path.resolve() if repo_path is not None else _checkout_repo(
            repo_url=repo_url,
            ref=ref,
            work_dir=checkout_root,
        )
        source_ref = _source_ref(source_path, ref if repo_path is None else None)
        source_commit = _source_commit(source_path)
        output_dir = (site_dir or (tmp_dir / "site")).resolve()

        knowledge_root = source_path / "docs" / "knowledge"
        diags = check_knowledge_base(knowledge_root, lean_root=source_path)
        error_count, warning_count = _diagnostic_counts(diags)
        if error_count:
            report = _diagnostic_report(diags)
            raise GateFailure(f"check reported {error_count} error(s), {warning_count} warning(s)\n{report}")

        publish(knowledge_root, output_dir)
        artifacts = verify_graph_artifacts(output_dir)
        verify_resolved_lean_links(output_dir)

        targets = _render_targets(output_dir, render_mode=render_mode, render_pages=render_pages or [])
        if targets:
            messages = asyncio.run(run_browser_render_check(output_dir, pages=targets, timeout_ms=timeout_ms))
            if messages:
                raise GateFailure("render_check reported issue(s)\n" + "\n".join(messages))

        return GateResult(
            source_path=source_path,
            source_ref=source_ref,
            source_commit=source_commit,
            site_dir=output_dir,
            error_count=error_count,
            warning_count=warning_count,
            render_pages=targets,
            artifacts=artifacts,
        )


def _print_result(result: GateResult) -> None:
    print(f"EconCSLib source: {result.source_path}")
    print(f"EconCSLib ref: {result.source_ref}")
    print(f"EconCSLib commit: {result.source_commit}")
    print(f"Generated site: {result.site_dir}")
    print(f"Check diagnostics: {result.error_count} error(s), {result.warning_count} warning(s)")
    if result.render_pages:
        print("Render-check pages:")
        for page in result.render_pages:
            print(f"  - {page.relative_to(result.site_dir).as_posix()}")
    else:
        print("Render-check pages: none")
    print("Verified graph artifacts:")
    for name, value in result.artifacts.items():
        if isinstance(value, list):
            print(f"  - {name}: {len(value)} file(s)")
        else:
            print(f"  - {name}: {value}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run mdblueprint's real EconCSLib integration gate.")
    parser.add_argument("--repo-path", type=Path, help="existing EconCSLib checkout to test")
    parser.add_argument("--repo-url", default=DEFAULT_REPO_URL, help="EconCSLib Git URL used when --repo-path is omitted")
    parser.add_argument("--ref", default=DEFAULT_REF, help="EconCSLib ref used when cloning")
    parser.add_argument("--work-dir", type=Path, help="checkout workspace used when cloning")
    parser.add_argument("--site-dir", type=Path, help="generated site output directory")
    parser.add_argument("--render-mode", choices=["smoke", "all", "none"], default="smoke")
    parser.add_argument("--render-page", action="append", default=[], help="relative page to render-check; may repeat")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        result = run_gate(
            repo_path=args.repo_path,
            repo_url=args.repo_url,
            ref=args.ref,
            work_dir=args.work_dir,
            site_dir=args.site_dir,
            render_mode=args.render_mode,
            render_pages=args.render_page,
            timeout_ms=args.timeout_ms,
        )
    except GateFailure as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    _print_result(result)


if __name__ == "__main__":
    main()
