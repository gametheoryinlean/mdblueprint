"""Browser-based render verification for published mdblueprint sites."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import re
import sys
import threading
from dataclasses import dataclass, field
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from tools.knowledge.renderer import TEX_MATH_RE


RAW_RENDERED_TEX_RE = re.compile(r"\\\(|\\\[|\$\$|(?<!\\)\$[^$\n]+(?<!\\)\$")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class KatexErrorDetail:
    expression: str
    title: str
    context: str


@dataclass(frozen=True)
class PageRenderState:
    path: Path
    had_math_source: bool
    body_text: str
    katex_count: int
    katex_error_count: int
    katex_errors: list[KatexErrorDetail] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)


def iter_html_pages(site_dir: Path) -> list[Path]:
    return sorted(path for path in site_dir.rglob("*.html") if path.is_file())


def html_has_math_source(html: str) -> bool:
    content = SCRIPT_STYLE_RE.sub("", html)
    return TEX_MATH_RE.search(content) is not None


def diagnose_render_state(state: PageRenderState) -> list[str]:
    messages: list[str] = []
    katex_failures = [url for url in state.failed_requests if "katex" in url.lower()]
    if katex_failures:
        messages.append(f"{state.path}: KaTeX asset failed to load: {', '.join(katex_failures)}")

    for error in state.console_errors:
        lowered = error.lower()
        if "katex" in lowered or "parseerror" in lowered or "render" in lowered:
            messages.append(f"{state.path}: browser console error: {error}")

    if state.katex_error_count:
        messages.append(f"{state.path}: KaTeX error elements present: {state.katex_error_count}")
        for index, error in enumerate(state.katex_errors, start=1):
            detail = f"{state.path}: KaTeX error {index}: expression: {error.expression}"
            if error.title:
                detail += f"; title: {error.title}"
            if error.context:
                detail += f"; context: {error.context}"
            messages.append(detail)

    if state.had_math_source and state.katex_count == 0:
        messages.append(f"{state.path}: source contains math but no rendered .katex elements were found")

    match = RAW_RENDERED_TEX_RE.search(state.body_text)
    if match:
        messages.append(f"{state.path}: raw TeX delimiter remains after browser rendering: {match.group(0)!r}")

    return messages


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


@contextlib.contextmanager
def _serve_site(site_dir: Path) -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(site_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


async def _capture_page_state(browser, base_url: str, site_dir: Path, path: Path, timeout_ms: int) -> PageRenderState:
    rel = path.relative_to(site_dir).as_posix()
    source = path.read_text(encoding="utf-8")
    console_errors: list[str] = []
    failed_requests: list[str] = []
    page = await browser.new_page()
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: console_errors.append(str(exc)))
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    try:
        # Deferred KaTeX scripts finish before DOMContentLoaded. Waiting for
        # networkidle is flaky across large CDN-backed sites.
        await page.goto(f"{base_url}/{rel}", wait_until="domcontentloaded", timeout=timeout_ms)
        if rel in {"dep_graph_document.html", "graph.html"}:
            try:
                await page.wait_for_selector("#graph .node[data-graph-node-id^='topic:']", timeout=timeout_ms)
                await page.locator("#graph .node[data-graph-node-id^='topic:']").first.click(timeout=timeout_ms)
                await page.wait_for_selector(
                    "#graph .node[data-graph-node-id]:not([data-graph-node-id^='topic:'])",
                    timeout=timeout_ms,
                )
                await page.locator(
                    "#graph .node[data-graph-node-id]:not([data-graph-node-id^='topic:'])"
                ).first.click(timeout=timeout_ms)
                await page.wait_for_selector("#node-detail-content .graph-modal-body", timeout=timeout_ms)
            except Exception as exc:  # Browser QA should surface lazy graph failures as render issues.
                console_errors.append(f"graph modal lazy payload did not open: {exc}")
            await page.evaluate(
                """() => {
                  document.querySelectorAll('.dep-modal-container').forEach((modal) => {
                    modal.hidden = false;
                  });
                }"""
            )
        await page.wait_for_timeout(100)
        body_text = await page.locator("body").inner_text(timeout=timeout_ms)
        katex_count = await page.locator(".katex").count()
        katex_error_count = await page.locator(".katex-error").count()
        katex_errors = [
            KatexErrorDetail(
                expression=item.get("expression", ""),
                title=item.get("title", ""),
                context=item.get("context", ""),
            )
            for item in await page.locator(".katex-error").evaluate_all(
                """elements => elements.map((element) => {
                  const container = element.closest('p, li, td, div, article, section, main, body');
                  const compact = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                  return {
                    expression: compact(element.textContent),
                    title: compact(element.getAttribute('title')),
                    context: compact(container ? container.textContent : '').slice(0, 500),
                  };
                })"""
            )
        ]
    finally:
        await page.close()

    return PageRenderState(
        path=path,
        had_math_source=html_has_math_source(source),
        body_text=body_text,
        katex_count=katex_count,
        katex_error_count=katex_error_count,
        katex_errors=katex_errors,
        console_errors=console_errors,
        failed_requests=failed_requests,
    )


async def run_browser_render_check(site_dir: Path, *, pages: list[Path] | None = None, timeout_ms: int = 10_000) -> list[str]:
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is required for browser render verification. "
            "Install it with `uv sync --extra browser` and install Chromium with "
            "`uv run --extra browser playwright install chromium`."
        ) from exc

    targets = pages if pages is not None else iter_html_pages(site_dir)
    messages: list[str] = []
    with _serve_site(site_dir) as base_url:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                for path in targets:
                    state = await _capture_page_state(browser, base_url, site_dir, path, timeout_ms)
                    messages.extend(diagnose_render_state(state))
            finally:
                await browser.close()
    return messages


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Verify rendered math in a published mdblueprint site.")
    parser.add_argument("site_dir", type=Path, help="published site directory")
    parser.add_argument("--page", action="append", default=[], help="relative HTML page to check; may be repeated")
    parser.add_argument("--timeout-ms", type=int, default=10_000, help="browser page timeout in milliseconds")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    pages = [args.site_dir / page for page in args.page] if args.page else None
    try:
        messages = asyncio.run(
            run_browser_render_check(args.site_dir, pages=pages, timeout_ms=args.timeout_ms)
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

    for message in messages:
        print(message)
    print(f"{len(messages)} render issue(s)")
    sys.exit(1 if messages else 0)


if __name__ == "__main__":
    main()
