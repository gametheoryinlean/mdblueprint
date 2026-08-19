"""Static Markdown-structure checks for knowledge nodes."""
from __future__ import annotations

from tools.knowledge.models import Node
from tools.knowledge.renderer import _FENCE_RE, _LIST_ITEM_RE
from tools.knowledge.validator import Diagnostic


def check_node_markdown(node: Node) -> list[Diagnostic]:
    """Return Markdown-structure diagnostics for a parsed knowledge node.

    The renderer inserts the missing blank line so the published page is
    correct either way; this warning exists so the source file matches what
    the author sees in a GitHub/CommonMark preview.
    """
    diags: list[Diagnostic] = []
    lines = node.body.split("\n")
    in_fence = False

    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or index == 0:
            continue

        match = _LIST_ITEM_RE.match(line)
        if match is None or (match.group(1) is not None and match.group(1) != "1"):
            continue

        previous = lines[index - 1]
        if (
            previous.strip() == ""
            or previous.startswith((" ", "\t"))
            or _LIST_ITEM_RE.match(previous)
            or previous.lstrip().startswith("#")
        ):
            continue

        diags.append(Diagnostic(
            "warning",
            node.id,
            f"line {index + 1}: list needs a blank line before it; "
            "Python-Markdown renders it as literal text without one",
            node.file_path,
            code="md-list-needs-blank-line",
        ))

    return diags
