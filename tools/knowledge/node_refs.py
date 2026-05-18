"""Node-reference syntax for mdblueprint Markdown bodies.

Syntax:
  [[node:<id>]]            — link; display text is the target node's title
  [[node:<id>|<label>]]    — link with custom display text

References to unknown node ids produce a checker diagnostic and render as
non-clickable unresolved spans.  Naked source-local references such as
"Lemma 6.2" trigger a warning diagnostic encouraging graph-aligned citations.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tools.knowledge.validator import Diagnostic

if TYPE_CHECKING:
    from tools.knowledge.models import Node

# Matches [[node:some.id]] and [[node:some.id|custom label]]
NODE_REF_RE = re.compile(
    r"\[\[node:([a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)(?:\|([^\]\n]+))?\]\]"
)

# Naked source-local references like "Lemma 6.2", "Theorem 8.1.2", etc.
NAKED_SRC_REF_RE = re.compile(
    r"\b(Lemma|Proposition|Theorem|Corollary|Definition|Remark|Example|Claim)"
    r"\s+\d+(?:\.\d+)*\b"
)

_PROOF_SPLIT_RE = re.compile(
    r"(?im)(?:^|\n)(?:\s*(?:\*{1,2}Proof\.\*{1,2}|Proof\.|##\s+Proof)\s*)"
)

THEOREM_KINDS: frozenset[str] = frozenset({"theorem", "proposition", "lemma", "corollary"})


def _split_body_proof(body: str) -> tuple[str, str | None]:
    m = _PROOF_SPLIT_RE.search(body)
    if m is None:
        return body, None
    return body[: m.start()], body[m.end():]


def check_node_body_refs(node: "Node", all_nodes: dict[str, "Node"]) -> list[Diagnostic]:
    """Check node body for unknown/misaligned node references and naked source citations."""
    diags: list[Diagnostic] = []
    body = node.body or ""

    # (1) Any [[node:id]]: error if id is not in the node index
    for m in NODE_REF_RE.finditer(body):
        ref_id = m.group(1)
        if ref_id not in all_nodes:
            diags.append(Diagnostic(
                "error",
                node.id,
                f"unknown node reference [[node:{ref_id}]]",
                node.file_path,
            ))

    # (2) Theorem-like nodes: proof [[node:id]] refs should be in uses
    if node.kind in THEOREM_KINDS:
        _, proof_text = _split_body_proof(body)
        if proof_text:
            uses_set = set(node.uses or [])
            for m in NODE_REF_RE.finditer(proof_text):
                ref_id = m.group(1)
                if ref_id in all_nodes and ref_id not in uses_set:
                    diags.append(Diagnostic(
                        "warning",
                        node.id,
                        f"proof references [[node:{ref_id}]] but {ref_id!r} is not listed in uses",
                        node.file_path,
                    ))

    # (3) Naked source-local references
    for m in NAKED_SRC_REF_RE.finditer(body):
        diags.append(Diagnostic(
            "warning",
            node.id,
            f"ambiguous source-local reference {m.group()!r}; "
            "use [[node:id]] for graph-aligned references or a source locator for external citations",
            node.file_path,
        ))

    return diags
