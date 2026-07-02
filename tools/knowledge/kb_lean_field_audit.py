"""Audit KB body-prose coverage of Lean structure / class / inductive fields.

For every KB node that declares a ``structure``, ``class``, or ``inductive``
in its ``lean.declarations`` YAML, this audit:

1. Extracts the fields from the Lean signature (via the LeanIndex signature
   snippet — which now includes ``where``-block bodies).
2. Checks whether the field is *plausibly* referenced in the KB body prose,
   using several heuristics:
     - explicit backtick mention of the field name (``` `P0` ```);
     - inline `(P0)` / `**(P0)**` style axiom labels (common in this
       codebase);
     - the field's docstring extracted from ``/-- ... -/`` above the
       field — its lowercase content is searched in body prose.
3. Reports uncovered fields.  For each finding it emits both the raw
   fact and a hint for the Agent about *what* to add to the KB body.

The audit output is Agent-actionable Markdown suitable for feeding back
into an authoring loop.  Zero findings = every declared class/structure's
fields are visibly covered in the KB body.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tools.knowledge.config import ProjectConfig
from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex

_STRUCTURED_KINDS = {"structure", "class", "inductive"}

# Field: `  name : type` or `  name :\n    type`, with optional attribute
# annotations.  Skips docstring lines (`/--`) and closing `-/`.
_FIELD_LINE_RE = re.compile(
    r"^\s+([A-Za-z_][\w']*)\s*[:∈]",
)

# `/-- (P0) Cosheaf monotonicity: ... -/` — extract the parenthesised
# axiom tag `(P0)` and the natural-language description.
_DOCSTRING_TAG_RE = re.compile(r"\(([A-Z][A-Za-z0-9_]*)\)")


@dataclass(frozen=True)
class LeanField:
    name: str
    docstring: str | None = None

    @property
    def axiom_tag(self) -> str | None:
        """Extract `(P0)` / `(K3)` style tag from the docstring, if any."""
        if self.docstring is None:
            return None
        m = _DOCSTRING_TAG_RE.search(self.docstring)
        return m.group(1) if m else None


@dataclass
class FieldAuditFinding:
    node_id: str
    node_path: Path | None
    declaration: str
    field: LeanField

    def as_markdown(self) -> str:
        if self.node_path is None:
            loc = "_(unknown)_"
        else:
            try:
                loc = f"{self.node_path.relative_to(Path.cwd())}"
            except ValueError:
                loc = str(self.node_path)
        tag = self.field.axiom_tag
        tag_str = f" (tag `({tag})`)" if tag else ""
        doc = self.field.docstring or ""
        doc_short = (doc[:120] + "…") if len(doc) > 120 else doc
        hint = self._suggest_hint()
        return (
            f"- **{self.node_id}** → `{self.declaration}`.`{self.field.name}`{tag_str}\n"
            f"  - File: `{loc}`\n"
            f"  - Docstring: {doc_short or '_(no docstring)_'}\n"
            f"  - Suggestion: {hint}"
        )

    def _suggest_hint(self) -> str:
        tag = self.field.axiom_tag
        name = self.field.name
        if tag:
            return (
                f"Add an axiom bullet or Definition clause labelled "
                f"**({tag})** to the body prose, covering the content of "
                f"`{name}`."
            )
        return (
            f"Reference the field `{name}` in the body — either as a "
            f"backticked identifier or as a mathematical axiom / component "
            f"of the definition."
        )


def extract_fields_from_signature(sig: str) -> list[LeanField]:
    """Parse a ``structure`` / ``class`` / ``inductive`` signature body
    into a list of fields with docstrings.
    """
    if not sig:
        return []
    lines = sig.splitlines()
    # Skip the header (everything up to and including the ` where` line).
    where_index = None
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.endswith(" where") or stripped == "where":
            where_index = i
            break
    if where_index is None:
        return []

    fields: list[LeanField] = []
    pending_doc: list[str] = []
    in_doc = False

    for ln in lines[where_index + 1:]:
        stripped = ln.strip()
        if stripped.startswith("/--"):
            in_doc = True
            pending_doc = [stripped[3:].strip()]
            # Docstring may close on the same line: `/-- foo -/`
            if stripped.endswith("-/"):
                pending_doc[-1] = pending_doc[-1][:-2].strip()
                in_doc = False
            continue
        if in_doc:
            body = stripped
            if body.endswith("-/"):
                body = body[:-2].strip()
                in_doc = False
            pending_doc.append(body)
            continue
        m = _FIELD_LINE_RE.match(ln)
        if m:
            name = m.group(1)
            doc = " ".join(p for p in pending_doc if p).strip() or None
            fields.append(LeanField(name=name, docstring=doc))
            pending_doc = []
    return fields


def field_covered_in_body(field: LeanField, body: str) -> bool:
    """Return True if this field's presence is plausibly acknowledged in
    the KB body prose.  Uses multiple heuristics — the goal is
    *conservative* detection (mark as covered when there is any real
    signal), because false-positive findings are more expensive than
    false-negative ones during author-driven audit.
    """
    body_lower = body.lower()
    # 1) Backtick mention of the field name.
    if f"`{field.name}`" in body:
        return True
    # 1b) LaTeX math mention `$P$`, `$P_E$`, `$P_x$`, or as an item of a
    # family `$P = ...$`.  For short data fields (`P`, `Q`, `R`, …) the
    # body typically references them with LaTeX math delimiters, not
    # backticks.  Detect the identifier at a word boundary inside `$…$`.
    if re.search(rf"\$[^$]*(?<![A-Za-z_]){re.escape(field.name)}(?![A-Za-z0-9_'])", body):
        return True
    # 2) Axiom tag from docstring: (P0), (K3), etc.
    tag = field.axiom_tag
    if tag:
        # `(P0)` — the axiom tag in inline text.
        if f"({tag})" in body:
            return True
        # `**(P0)**` — the bolded version common in the codebase.
        if f"**({tag})**" in body:
            return True
    # 3) Non-underscored field name as a keyword: at least one occurrence
    # of the base name (before any prime or subscript-like suffix).  This
    # catches "orbit_iff" referenced as "orbit" in prose, "G'_le_stab"
    # referenced as "$G' \le \Stab_G(X')$", etc.  Very loose — the
    # docstring check below is the primary signal.
    base = field.name.split("_")[0].lower().rstrip("'")
    if base and len(base) >= 3 and base in body_lower:
        return True
    # 4) Docstring keyword overlap: pick up "cosheaf monotonicity" etc.
    if field.docstring:
        # Take substantive words (length >= 6) from the docstring,
        # excluding the axiom tag.  If any appears verbatim in body,
        # consider it covered.
        doc = field.docstring
        # Remove the parenthetical tag.
        doc = _DOCSTRING_TAG_RE.sub("", doc)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{5,}", doc):
            if token.lower() in body_lower:
                return True
    return False


def audit_node(node, idx: LeanIndex) -> list[FieldAuditFinding]:
    findings: list[FieldAuditFinding] = []
    if node.lean is None or not node.lean.declarations:
        return findings
    for decl_name in node.lean.declarations:
        decl = idx.declarations.get(decl_name)
        if decl is None:
            continue
        if decl.kind not in _STRUCTURED_KINDS:
            continue
        for field in extract_fields_from_signature(decl.signature or ""):
            if not field_covered_in_body(field, node.body):
                findings.append(
                    FieldAuditFinding(
                        node_id=node.id,
                        node_path=node.file_path,
                        declaration=decl_name,
                        field=field,
                    )
                )
    return findings


def audit_knowledge_base(
    ctx: KnowledgeContext,
    lean_idx: LeanIndex,
) -> list[FieldAuditFinding]:
    findings: list[FieldAuditFinding] = []
    for node in ctx.nodes_by_id.values():
        findings.extend(audit_node(node, lean_idx))
    return findings


def render_report(findings: list[FieldAuditFinding]) -> str:
    if not findings:
        return "# KB↔Lean field-coverage audit\n\nNo findings — every declared `structure`/`class`/`inductive` field is referenced in its node's body prose.\n"
    lines = [
        "# KB↔Lean field-coverage audit",
        "",
        f"Found **{len(findings)}** uncovered field(s).  For each finding, the",
        "field appears in the Lean declaration listed in the node's YAML but",
        "is not visibly referenced (by name, axiom tag, or docstring keyword)",
        "in the node's body prose.  The suggestions are Agent-actionable —",
        "each maps to a specific edit in the KB body.",
        "",
    ]
    by_node: dict[str, list[FieldAuditFinding]] = {}
    for f in findings:
        by_node.setdefault(f.node_id, []).append(f)
    for node_id, group in sorted(by_node.items()):
        lines.append(f"## {node_id}")
        lines.append("")
        for f in group:
            lines.append(f.as_markdown())
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("knowledge_root", type=Path)
    parser.add_argument(
        "--lean-root",
        type=Path,
        default=None,
        help="Root of the Lean project to index. Defaults to the resolved "
        "`local_path` of the node's default repository.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write the report to this file instead of stdout.",
    )
    args = parser.parse_args()

    ctx = KnowledgeContext.load(args.knowledge_root)
    from tools.knowledge.lean_index import index_lean_project

    lean_root = args.lean_root
    if lean_root is None:
        cfg = ctx.config.lean
        if not cfg.repositories:
            print("no lean repository configured", file=sys.stderr)
            sys.exit(2)
        default = cfg.repositories[0]
        lean_root = (args.knowledge_root.parent / default.local_path).resolve()

    idx = index_lean_project(lean_root)
    findings = audit_knowledge_base(ctx, idx)
    report = render_report(findings)
    if args.output is not None:
        args.output.write_text(report)
    else:
        print(report)
    sys.exit(0 if not findings else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
