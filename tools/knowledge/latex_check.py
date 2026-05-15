"""Static preflight diagnostics for TeX snippets in node bodies."""
from __future__ import annotations

import re

from tools.knowledge.models import Node
from tools.knowledge.validator import Diagnostic


MATH_DELIMITER_RE = re.compile(r"(?<!\\)\$\$|(?<!\\)\$|\\\(|\\\)|\\\[|\\\]")
ENVIRONMENT_RE = re.compile(r"\\(begin|end)\{([^{}]+)\}")


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def check_node_math(node: Node) -> list[Diagnostic]:
    """Return syntax-level TeX diagnostics for a parsed knowledge node."""
    diags: list[Diagnostic] = []
    stack: list[tuple[str, int]] = []

    def err(message: str) -> None:
        diags.append(Diagnostic("error", node.id, message, node.file_path))

    def warn(message: str) -> None:
        diags.append(Diagnostic("warning", node.id, message, node.file_path))

    for match in MATH_DELIMITER_RE.finditer(node.body):
        token = match.group(0)
        line = _line_number(node.body, match.start())

        if token in {"$", "$$", r"\(", r"\["}:
            if stack and stack[-1][0] == token and token in {"$", "$$"}:
                stack.pop()
            else:
                stack.append((token, line))
            continue

        expected = {r"\)": r"\(", r"\]": r"\["}[token]
        if stack and stack[-1][0] == expected:
            stack.pop()
        else:
            err(f"line {line}: unmatched closing math delimiter {token!r}")

    for token, line in stack:
        err(f"line {line}: unmatched math delimiter {token!r}")

    env_stack: list[tuple[str, int]] = []
    for match in ENVIRONMENT_RE.finditer(node.body):
        kind = match.group(1)
        env = match.group(2)
        line = _line_number(node.body, match.start())
        if kind == "begin":
            env_stack.append((env, line))
            continue

        if not env_stack:
            err(f"line {line}: unmatched \\end{{{env}}}")
            continue

        open_env, open_line = env_stack.pop()
        if open_env != env:
            err(
                f"line {line}: mismatched environment \\begin{{{open_env}}} "
                f"from line {open_line} closed by \\end{{{env}}}"
            )

    for env, line in env_stack:
        err(f"line {line}: unmatched \\begin{{{env}}}")

    for line_number, line in enumerate(node.body.splitlines(), start=1):
        if "|" in line and (r"\[" in line or "$$" in line or r"\begin{" in line):
            warn(f"line {line_number}: display math inside a Markdown table cell may render poorly")

    return diags
