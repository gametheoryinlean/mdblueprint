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


_SEE_ALSO_HEADING_RE = re.compile(
    r"(?im)^##+\s+(?:See also|Where used|Applications?|Related|"
    r"Remarks?|Comparison|Why this matters|Editorial note|Status|"
    r"Future work|Notes?|References?|Comment|Alternative source|"
    r"Alternative sources?|Discussion)\s*(?:\(.*\))?$"
)


def _strip_see_also_sections(text: str) -> str:
    """Drop everything after a "See also"/"Where used"/etc. heading.

    These sections are discursive remarks pointing at downstream
    consumers; the `[[node:...]]` refs they contain are not logical
    dependencies and would create cycles if added to `uses`.
    """
    m = _SEE_ALSO_HEADING_RE.search(text)
    if m is None:
        return text
    return text[: m.start()]


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

    # (2) Theorem-like nodes: proof [[node:id]] refs should be in uses.
    # We exclude "see-also" sections (after `## See also`, `## Where used`,
    # `## Applications`, `## Related`, `## Remarks` headings — these are
    # discursive remarks, not part of the proof). We also exclude refs
    # that appear inside a markdown quote-marked Note/Remark block.
    if node.kind in THEOREM_KINDS:
        _, proof_text = _split_body_proof(body)
        if proof_text:
            # Strip out "see also"-style sections from proof_text before checking.
            proof_text = _strip_see_also_sections(proof_text)
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

    # (3) Naked source-local references — skip the following:
    #   (a) inside a bracketed external citation `[Yu Lemma 12.4]`
    #   (b) inside a `[[node:id|...label...]]` link label
    #   (c) local self-reference "Lemma N" / "Theorem N" referring to
    #       a statement defined in the same file (i.e. there's a
    #       `> **Lemma N**` or `\begin{...}\label{...N...}` earlier
    #       in the body matching the bare integer)
    body_inline_labels = set(re.findall(
        r"^>?\s*\*\*([A-Z][a-z]+ \d+(?:\.\d+)*)",  # `> **Lemma 1**` or `> **Theorem 5.2**`
        body, flags=re.M
    ))
    for m in NAKED_SRC_REF_RE.finditer(body):
        text = m.group()
        # (c) skip self-references
        if text in body_inline_labels:
            continue
        start = m.start()
        # (a) skip bracketed external citations `[X ... text ...]`
        prefix = body[max(0, start - 120):start]
        last_open_sq = prefix.rfind("[")
        last_close_sq = prefix.rfind("]")
        if last_open_sq > last_close_sq:
            suffix = body[m.end():m.end() + 80]
            if "]" in suffix:
                close_at = suffix.index("]")
                open_at = suffix.index("[") if "[" in suffix else len(suffix) + 1
                if close_at < open_at:
                    # Also check this isn't a `[[node:...]]` itself by
                    # looking back further.
                    if not body[max(0, start - 150):start].rstrip().endswith("[[node:"):
                        # Bracketed citation. Skip.
                        # But: if the previous `[` is part of `[[`, it's a node
                        # link, fall through to (b).
                        if prefix[last_open_sq - 1:last_open_sq + 1] != "[[":
                            continue
        # (b) skip if we're inside a `[[node:id|label]]` — look for
        # `[[node:` before the match without a closing `]]`.
        # Find unmatched `[[node:` in the prefix.
        node_link_open = prefix.rfind("[[node:")
        if node_link_open >= 0:
            # Check there's no `]]` between node_link_open and start.
            inter = prefix[node_link_open:]
            if "]]" not in inter:
                # Look for closing `]]` after the match.
                suffix2 = body[m.end():m.end() + 80]
                if "]]" in suffix2:
                    continue

        diags.append(Diagnostic(
            "warning",
            node.id,
            f"ambiguous source-local reference {m.group()!r}; "
            "use [[node:id]] for graph-aligned references or a source locator for external citations",
            node.file_path,
        ))

    return diags
