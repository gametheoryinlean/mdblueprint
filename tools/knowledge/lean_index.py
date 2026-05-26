"""Extract Lean 4 declarations from source files into an index."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tools.knowledge.config import LeanRepositoryConfig


DECL_KEYWORDS = re.compile(
    r"^(def|theorem|lemma|abbrev|instance|structure|class|inductive|"
    r"noncomputable def|noncomputable instance|"
    r"protected def|protected theorem|protected lemma|"
    r"private def|private theorem|private lemma)\s+",
)

_CANONICAL_KIND: dict[str, str] = {
    "noncomputable def": "def",
    "noncomputable instance": "instance",
    "protected def": "def",
    "protected theorem": "theorem",
    "protected lemma": "lemma",
    "private def": "def",
    "private theorem": "theorem",
    "private lemma": "lemma",
}

SORRY_RE = re.compile(r"\bsorry\b")
ADMIT_RE = re.compile(r"\badmit\b")
NAMESPACE_RE = re.compile(r"^namespace\s+(\S+)")
SECTION_RE = re.compile(r"^section(?:\s+(\S+))?\s*$")
END_NAMED_RE = re.compile(r"^end\s+(\S+)")
END_BARE_RE = re.compile(r"^end\s*$")


@dataclass(frozen=True)
class LeanDeclaration:
    name: str
    qualified_name: str
    kind: str
    file: Path
    line: int
    module: str | None = None
    signature: str | None = None
    docstring: str | None = None
    namespace: str | None = None
    has_sorry: bool = False
    repository_id: str | None = None
    repository_title: str | None = None
    revision: str | None = None
    relative_path: str | None = None
    source_url: str | None = None
    doc_url: str | None = None
    # Blueprint node ids this declaration self-identifies as backing.
    # Populated by parsing `Blueprint: ...` markers in the
    # declaration's `/-- ... -/` docstring, plus any module-level
    # `## Blueprint` section in the file's `/-! ... -/` header.
    # Empty tuple by default; back-compatible.
    blueprint_nodes: tuple[str, ...] = ()


@dataclass
class LeanIndex:
    declarations: dict[str, LeanDeclaration] = field(default_factory=dict)
    sorry_decls: list[str] = field(default_factory=list)
    modules: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _extract_decl_name(line: str) -> tuple[str, str] | None:
    m = DECL_KEYWORDS.match(line.lstrip())
    if m is None:
        return None
    keyword = m.group(1)
    canonical = _CANONICAL_KIND.get(keyword, keyword)
    rest = line.lstrip()[m.end():]
    name_match = re.match(r"(\S+)", rest)
    if name_match is None:
        return None
    name = name_match.group(1).rstrip(":")
    if "{" in name or "(" in name or "[" in name:
        return None
    return canonical, name


def _module_name(file: Path, lean_root: Path) -> str:
    rel = file.relative_to(lean_root)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def build_module_source_metadata(
    lean_file: Path,
    lean_root: Path,
    repository: LeanRepositoryConfig | None,
    *,
    line: int = 1,
) -> dict[str, str | None]:
    """Public helper: build source metadata for a Lean file (not a single
    declaration). Defaults to line 1 so callers that point at a whole
    module get the top of the file. Returns the same shape as the
    per-declaration metadata so it can be merged into ref payloads.
    """
    return _source_metadata(lean_file, line, lean_root, repository)


_SUGGEST_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]+")


def _suggest_tokens(text: str) -> set[str]:
    spaced = text.replace("_", " ").replace("-", " ").replace(".", " ")
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)
    return {
        tok
        for tok in (m.lower() for m in _SUGGEST_TOKEN_RE.findall(spaced))
        if len(tok) > 1
    }


def suggest_for_unresolved(name: str, idx: "LeanIndex", *, k: int = 3) -> list[str]:
    """Cheap "did you mean" lookup for unresolved Lean references.

    Strategy (in order, deduped, top-k):
    1. Suffix match: qualified names ending with ``.{last_segment}``.
    2. Module match: if ``name`` is itself a module name in the index,
       surface as ``(module) X`` so the user can move it from
       ``lean.declarations`` to ``lean.modules``.
    3. Token overlap: rank by lowercase token-set intersection size,
       ties broken alphabetically.

    Returns at most ``k`` human-readable suggestions; empty list when
    the index has nothing to suggest from.
    """
    if not idx.declarations and not idx.modules:
        return []
    suggestions: list[str] = []
    seen: set[str] = set()

    last_segment = name.rsplit(".", 1)[-1]
    if last_segment and last_segment != name:
        for qualified in idx.declarations:
            if qualified.endswith(f".{last_segment}") and qualified not in seen:
                suggestions.append(qualified)
                seen.add(qualified)
                if len(suggestions) >= k:
                    return suggestions

    if name in idx.modules:
        marker = f"(module) {name}"
        if marker not in seen:
            suggestions.append(marker)
            seen.add(marker)
            if len(suggestions) >= k:
                return suggestions

    target_tokens = _suggest_tokens(name)
    if not target_tokens:
        return suggestions

    scored: list[tuple[int, str]] = []
    for qualified in idx.declarations:
        if qualified in seen:
            continue
        overlap = len(target_tokens & _suggest_tokens(qualified))
        if overlap:
            scored.append((overlap, qualified))
    for module_name in idx.modules:
        marker = f"(module) {module_name}"
        if marker in seen:
            continue
        overlap = len(target_tokens & _suggest_tokens(module_name))
        if overlap:
            scored.append((overlap, marker))

    scored.sort(key=lambda item: (-item[0], item[1]))
    for _, candidate in scored:
        if candidate not in seen:
            suggestions.append(candidate)
            seen.add(candidate)
            if len(suggestions) >= k:
                break
    return suggestions


def _source_metadata(
    lean_file: Path,
    line: int,
    lean_root: Path,
    repository: LeanRepositoryConfig | None,
    *,
    module: str | None = None,
    qualified_name: str | None = None,
) -> dict[str, str | None]:
    if repository is None:
        return {
            "repository_id": None,
            "repository_title": None,
            "revision": None,
            "relative_path": None,
            "source_url": None,
            "doc_url": None,
        }

    relative_path = lean_file.relative_to(lean_root).as_posix()
    template_path = (
        f"{repository.subdir}/{relative_path}" if repository.subdir else relative_path
    )
    source_url = repository.source_url_template.format(
        web_url=repository.web_url.rstrip("/"),
        revision=repository.revision,
        path=template_path,
        line=line,
    )
    doc_url: str | None = None
    if repository.doc_url_template:
        derived_module = module
        if derived_module is None:
            derived_module = Path(relative_path).with_suffix("").as_posix().replace("/", ".")
        derived_module_html = derived_module.replace(".", "/")
        try:
            doc_url = repository.doc_url_template.format(
                web_url=repository.web_url.rstrip("/"),
                revision=repository.revision,
                module=derived_module,
                module_html=derived_module_html,
                qualified_name=qualified_name or "",
            )
        except (KeyError, IndexError):
            # Bad template variable -> degrade gracefully to no doc link
            # rather than crashing the whole publish.
            doc_url = None
    return {
        "repository_id": repository.id,
        "repository_title": repository.title,
        "revision": repository.revision,
        "relative_path": relative_path,
        "source_url": source_url,
        "doc_url": doc_url,
    }


def _decl_location(decl: LeanDeclaration) -> str:
    if decl.repository_id and decl.revision and decl.relative_path:
        return f"{decl.repository_id}@{decl.revision}:{decl.relative_path}:{decl.line}"
    return f"{decl.file}:{decl.line}"


def _docstring_before(lines: list[str], decl_index: int) -> str | None:
    previous = decl_index - 1
    while previous >= 0 and not lines[previous].strip():
        previous -= 1
    if previous < 0:
        return None
    line = lines[previous].strip()
    if line.startswith("/--") and line.endswith("-/"):
        return line[3:-2].strip()
    return None


# Matches `Blueprint:` (case-insensitive) at the start of a docstring line,
# capturing the trailing comma/whitespace-separated list of node ids.
_BLUEPRINT_LINE_RE = re.compile(r"^\s*Blueprint\s*:\s*(.+?)\s*$", re.IGNORECASE)

# A blueprint node id is at least topic.something — dotted, allowing
# underscores and alphanumerics. The trailing punctuation (period,
# comma, backticks, parentheses) is stripped during extraction.
_NODE_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+")


def _extract_node_ids(text: str) -> list[str]:
    """Pull every dotted node-id-shaped token out of `text`.

    Used by both the module-level `## Blueprint` parser and the
    declaration-level `Blueprint:` line parser. Empty / no-match input
    returns an empty list.
    """
    if not text:
        return []
    return _NODE_ID_RE.findall(text)


def _full_docstring_before(lines: list[str], decl_index: int) -> tuple[str | None, int]:
    """Like `_docstring_before` but also returns the multi-line variant.

    Returns `(content, num_consumed_lines)` so callers can rewind past
    the docstring. The `content` is the joined inner body (without the
    `/--` / `-/` delimiters). Returns `(None, 0)` if no docstring
    immediately precedes the declaration.
    """
    cursor = decl_index - 1
    while cursor >= 0 and not lines[cursor].strip():
        cursor -= 1
    if cursor < 0:
        return None, 0

    end_line = lines[cursor].rstrip()
    # Single-line form `/-- ... -/`
    if end_line.lstrip().startswith("/--") and end_line.rstrip().endswith("-/"):
        inner = end_line.strip()[3:-2].strip()
        return inner, 1

    # Multi-line form: walk backwards until `/--` is found
    if not end_line.rstrip().endswith("-/"):
        return None, 0
    start = cursor
    while start >= 0 and not lines[start].lstrip().startswith("/--"):
        start -= 1
    if start < 0:
        return None, 0
    # Inner body: drop `/--` from the first line and `-/` from the last
    body_lines = list(lines[start:cursor + 1])
    if not body_lines:
        return None, 0
    body_lines[0] = body_lines[0].lstrip()[3:]
    body_lines[-1] = body_lines[-1].rstrip()[:-2]
    return "\n".join(body_lines).strip(), cursor - start + 1


def _module_blueprint_nodes(lines: list[str]) -> list[str]:
    """Extract node ids from a module-level `/-! ... -/` header block.

    Looks for the first `/-!` ... `-/` block in the file (typically the
    module docstring) and pulls node ids out of any `## Blueprint`
    (or `Blueprint:` on its own line) section. Returns an empty list
    if no such block exists, or no marker is found.
    """
    if not lines:
        return []

    # Locate the `/-!` opener (must be in the leading comment block,
    # before any `import` / declaration).
    start = -1
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith("/-!"):
            start = i
            break
        if stripped.startswith("/--"):
            # `/--` is a declaration docstring, not a module docstring.
            break
        # Anything substantive before `/-!` -> no module docstring.
        if stripped and not stripped.startswith("--") and not stripped.startswith("import"):
            break

    if start < 0:
        return []

    end = -1
    for j in range(start, len(lines)):
        if "-/" in lines[j]:
            end = j
            break
    if end < 0:
        return []

    block = lines[start:end + 1]
    # Find the `## Blueprint` section (or a bare `Blueprint:` line) and
    # accumulate node ids until the next `##` header or end of block.
    nodes: list[str] = []
    collecting = False
    for raw in block:
        stripped = raw.strip()
        if not collecting:
            if stripped.startswith("##"):
                heading = stripped.lstrip("#").strip().lower()
                if heading.startswith("blueprint"):
                    collecting = True
                    # `## Blueprint: foo.bar` - inline form
                    if ":" in heading:
                        _, inline = heading.split(":", 1)
                        nodes.extend(_extract_node_ids(inline))
            else:
                m = _BLUEPRINT_LINE_RE.match(stripped)
                if m:
                    nodes.extend(_extract_node_ids(m.group(1)))
        else:
            # End collecting at the next `##` heading
            if stripped.startswith("##"):
                break
            nodes.extend(_extract_node_ids(stripped))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for node in nodes:
        if node not in seen:
            seen.add(node)
            unique.append(node)
    return unique


def _declaration_blueprint_nodes(docstring: str | None) -> list[str]:
    """Extract node ids from a per-declaration docstring.

    Recognises a `Blueprint:` line anywhere in the docstring body.
    Returns deduped node ids preserving order.
    """
    if not docstring:
        return []
    nodes: list[str] = []
    for line in docstring.splitlines():
        m = _BLUEPRINT_LINE_RE.match(line)
        if m:
            nodes.extend(_extract_node_ids(m.group(1)))
    seen: set[str] = set()
    unique: list[str] = []
    for node in nodes:
        if node not in seen:
            seen.add(node)
            unique.append(node)
    return unique


def _signature_snippet(lines: list[str], decl_index: int, *, max_lines: int = 12) -> str:
    collected: list[str] = []
    for offset in range(decl_index, min(decl_index + max_lines, len(lines))):
        raw = lines[offset].rstrip()
        if offset > decl_index and DECL_KEYWORDS.match(raw.lstrip()):
            break
        if ":=" in raw:
            before = raw.split(":=", 1)[0].rstrip()
            if before:
                collected.append(before)
            break
        collected.append(raw)
        stripped = raw.strip()
        if stripped.endswith(" where") or stripped == "where":
            break
    return "\n".join(line for line in collected if line.strip()).strip()


def index_lean_project(lean_root: Path, *, repository: LeanRepositoryConfig | None = None) -> LeanIndex:
    idx = LeanIndex()

    for lean_file in sorted(lean_root.rglob("*.lean")):
        module = _module_name(lean_file, lean_root)
        idx.modules[module] = lean_file

        try:
            lines = lean_file.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        scope_stack: list[tuple[str, str | None]] = []
        module_blueprint_nodes = _module_blueprint_nodes(lines)

        for lineno, line in enumerate(lines, start=1):
            # Track namespace/section scopes
            ns_match = NAMESPACE_RE.match(line)
            if ns_match:
                scope_stack.append(("namespace", ns_match.group(1)))
                continue
            section_match = SECTION_RE.match(line)
            if section_match:
                scope_stack.append(("section", section_match.group(1)))
                continue
            end_named = END_NAMED_RE.match(line)
            if end_named:
                name = end_named.group(1)
                if scope_stack and scope_stack[-1][1] == name:
                    scope_stack.pop()
                continue
            if END_BARE_RE.match(line):
                if scope_stack:
                    scope_stack.pop()
                continue

            result = _extract_decl_name(line)
            if result is None:
                continue
            keyword, name = result

            prefix = ".".join(name for kind, name in scope_stack if kind == "namespace" and name)
            qualified = f"{prefix}.{name}" if prefix else name

            # Check for sorry in the declaration body up to the next declaration
            next_decl_line = len(lines)
            for i in range(lineno, min(lineno + 50, len(lines))):
                if i == lineno - 1:
                    continue
                if DECL_KEYWORDS.match(lines[i].lstrip()):
                    next_decl_line = i
                    break
            body_text = "\n".join(lines[lineno - 1:next_decl_line])
            has_sorry = bool(SORRY_RE.search(body_text)) or bool(ADMIT_RE.search(body_text))

            # Look up the full (possibly multi-line) docstring so we can
            # extract any `Blueprint:` marker. `_docstring_before` only
            # returns single-line content; falls back to the full text
            # otherwise.
            full_docstring, _consumed = _full_docstring_before(lines, lineno - 1)
            decl_blueprint = _declaration_blueprint_nodes(full_docstring)
            # Merge with module-level markers, deduping while keeping
            # per-decl markers first (they're more specific).
            merged_nodes: list[str] = list(decl_blueprint)
            for node in module_blueprint_nodes:
                if node not in merged_nodes:
                    merged_nodes.append(node)

            decl = LeanDeclaration(
                name=name,
                qualified_name=qualified,
                kind=keyword,
                file=lean_file,
                line=lineno,
                module=module,
                signature=_signature_snippet(lines, lineno - 1),
                docstring=_docstring_before(lines, lineno - 1),
                namespace=prefix or None,
                has_sorry=has_sorry,
                blueprint_nodes=tuple(merged_nodes),
                **_source_metadata(
                    lean_file,
                    lineno,
                    lean_root,
                    repository,
                    module=module,
                    qualified_name=qualified,
                ),
            )
            if qualified in idx.declarations:
                prev = idx.declarations[qualified]
                idx.warnings.append(
                    f"duplicate declaration {qualified!r}: "
                    f"{_decl_location(prev)} and {_decl_location(decl)}"
                )
            idx.declarations[qualified] = decl
            if has_sorry:
                idx.sorry_decls.append(qualified)

    return idx


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m tools.knowledge.lean_index <lean_root>")
        sys.exit(1)
    lean_root = Path(sys.argv[1])
    idx = index_lean_project(lean_root)
    print(f"Indexed {len(idx.declarations)} declarations from {len(idx.modules)} modules")
    if idx.sorry_decls:
        print(f"\nDeclarations with sorry/admit ({len(idx.sorry_decls)}):")
        for name in sorted(idx.sorry_decls):
            decl = idx.declarations[name]
            print(f"  {name} ({decl.file}:{decl.line})")
    else:
        print("No sorry/admit found.")


if __name__ == "__main__":
    main()
