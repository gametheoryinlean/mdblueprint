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
    r"private def|private theorem|private lemma|"
    r"scoped instance|scoped def|scoped theorem|scoped lemma|"
    r"scoped abbrev)\s+",
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
    "scoped instance": "instance",
    "scoped def": "def",
    "scoped theorem": "theorem",
    "scoped lemma": "lemma",
    "scoped abbrev": "abbrev",
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


_ATTRIBUTE_PREFIX_RE = re.compile(r"^(?:@\[[^\]]*\]\s*)+")


def _extract_decl_name(line: str) -> tuple[str, str] | None:
    stripped = line.lstrip()
    # Skip any leading `@[…]` attribute blocks (e.g. `@[simp] theorem foo`).
    # A declaration can carry one or several attributes on the same line, so
    # match them greedily and strip.  Without this, `@[simp] theorem dim_smul`
    # would be silently missed by the index.
    stripped = _ATTRIBUTE_PREFIX_RE.sub("", stripped)
    m = DECL_KEYWORDS.match(stripped)
    if m is None:
        return None
    keyword = m.group(1)
    canonical = _CANONICAL_KIND.get(keyword, keyword)
    rest = stripped[m.end():]
    name_match = re.match(r"(\S+)", rest)
    if name_match is None:
        return None
    name = name_match.group(1).rstrip(":")
    if "{" in name or "(" in name or "[" in name:
        return None
    # Anonymous declarations (e.g. `noncomputable instance : T := ...`)
    # leave the regex matching a `:` token, which `.rstrip(":")`
    # collapses to the empty string. Skip them — indexing an empty
    # name produces qualified names ending in `.` which confuse the
    # downstream cross-checks.
    if not name:
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


def _leading_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _top_level_walrus_index(raw: str) -> int | None:
    """Return the byte index of a top-level `:=` in `raw`, or `None`.

    "Top-level" means at bracket depth zero — i.e., NOT inside `()`,
    `[]`, or `{}`.  This lets us distinguish the definition operator
    `:=` from Lean 4's *named-argument* syntax
    `(name := value)`, which routinely appears inside signatures
    (e.g. `(_d : InductionDatum (G := G) X')`) and must not be
    misparsed as the start of a definition body.
    """
    depth = 0
    i = 0
    n = len(raw)
    while i < n:
        c = raw[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and c == ":" and i + 1 < n and raw[i + 1] == "=":
            return i
        i += 1
    return None


# `where` at end of a declaration header opens a block whose semantics
# depend on the declaration kind:
#
#   * For `structure`, `class`, `inductive` the fields *are* the
#     declaration — the block belongs in the signature snippet.
#   * For `instance`, `def`, `abbrev` the block is the implementation of
#     a struct/typeclass; including it is useful (mirrors the historic
#     behaviour for `scoped instance category : ... where ...`).
#   * For `theorem`, `lemma`, `example` the block is a *proof body*
#     (fields like `mem_essImage q := by <tactics>`) which we
#     deliberately hide — a blueprint should surface the statement,
#     not the tactic script.
_WHERE_BLOCK_KINDS = frozenset({
    "structure", "class", "inductive",
    "instance", "def", "abbrev",
})


# Declaration kinds where a top-level `:=` opens a **body that IS the
# definition** (as opposed to a proof).  For these, if the body is short
# we prefer to include it in the snippet rather than truncating at `:=`.
#
#   * `abbrev`: alias definitions.  The RHS is the whole point
#     (`abbrev OrbitCat := X` — cutting at `:=` erases the definition).
#   * `def`, `instance`: term-level definitions and typeclass impls.
#     Short bodies are informative (`def Mor := {g : G // g • E ≤ E'}`);
#     long ones (multi-page term or tactic proof) still get cut.
#
# `theorem`, `lemma`, `example` are absent by design: their `:=` opens a
# proof, which the blueprint hides.
_INCLUDE_BODY_KINDS = frozenset({"abbrev", "def", "instance"})

# Maximum number of *continuation* lines past the `:=` line to include in
# the snippet.  Beyond this the body is assumed to be a full-blown
# implementation and we revert to cutting at `:=`.
_MAX_BODY_LOOKAHEAD = 4


def _peek_body_end(
    lines: list[str],
    walrus_line_idx: int,
    header_indent: int,
) -> int | None:
    """Return the exclusive end-line index of the body starting at
    `walrus_line_idx`, if the body terminates within
    `_MAX_BODY_LOOKAHEAD` continuation lines.  Otherwise return `None`.

    The body is considered to end at the first following line that is
    blank, starts a new top-level declaration keyword, or dedents back
    to `header_indent` or shallower.  Callers use this to decide whether
    the body is compact enough to inline in the snippet.
    """
    lookahead_end = walrus_line_idx + 1 + _MAX_BODY_LOOKAHEAD
    end = min(lookahead_end, len(lines))
    for i in range(walrus_line_idx + 1, end):
        raw = lines[i].rstrip()
        stripped = raw.strip()
        if not stripped:
            return i
        if DECL_KEYWORDS.match(raw.lstrip()):
            return i
        if _leading_indent(raw) <= header_indent:
            return i
    # End-of-file is a terminator too — a body that runs to EOF is
    # bounded whether or not we hit the lookahead cap.
    if end == len(lines):
        return len(lines)
    return None


def _signature_snippet(
    lines: list[str],
    decl_index: int,
    *,
    keyword: str = "",
    max_lines: int = 40,
) -> str:
    """Extract a Lean signature snippet from the actual source file.

    **This function is the single source of truth for Lean code display
    in the rendered blueprint pages.**  For every declaration name
    listed in a node's ``lean.declarations:`` frontmatter,
    :func:`index_lean_project` calls this extractor on the current
    Lean file at deploy time, and the returned string is what the
    renderer emits as the ``<pre class="lean-signature">`` block on
    the page.

    Design contract:

      * The signature returned always reflects the live Lean source
        as of the deploy commit — it cannot rot.
      * KB authors should NOT paste Lean signatures into
        ```` ```lean ```` fenced blocks in node body prose.  Such
        hand-written blocks silently drift out of sync when the
        underlying Lean is refactored; that failure mode is the whole
        reason this extractor exists.  The
        :class:`~tools.knowledge.lint._detectors.HandwrittenLeanBlockDetector`
        lint enforces this convention.

    Below is the extraction contract itself:

    For declarations that open a `where`-block (typically `class`,
    `structure`, `inductive`, and typeclass `instance`) the snippet
    extends through the block body — the fields *are* the definition,
    so showing only the header would misrepresent the declaration.
    The block ends at the first line whose indentation returns to the
    declaration's own indent (or shallower) and is non-blank, or when
    we hit another top-level `DECL_KEYWORDS` match, whichever comes
    first.

    For `theorem`, `lemma`, `example` a trailing `where` opens a *proof
    body* (Prop-valued structure with fields inhabited by tactic
    scripts); we STOP at the `where` line rather than exposing the
    proof.  Callers that want the proof body should read the source
    directly.

    For declarations bounded by a top-level `:=` (typical `def`,
    `theorem`, `lemma`) the snippet is cut just before that `:=`.
    Named-argument syntax `(name := value)` inside brackets is *not*
    treated as the definition operator.

    `max_lines` caps the total captured region, so a very long `where`-
    block stays reasonable.
    """
    if decl_index >= len(lines):
        return ""
    header_indent = _leading_indent(lines[decl_index])
    collected: list[str] = []
    in_where_block = False
    allow_where_block = keyword in _WHERE_BLOCK_KINDS
    include_body = keyword in _INCLUDE_BODY_KINDS

    for offset in range(decl_index, min(decl_index + max_lines, len(lines))):
        raw = lines[offset].rstrip()
        stripped_full = raw.strip()

        if offset > decl_index:
            # Bail on the next top-level declaration keyword regardless of block state.
            if DECL_KEYWORDS.match(raw.lstrip()):
                break
            # In a `where` block, terminate when we dedent to the header's
            # indentation on a non-blank line — that means we've exited the
            # block body.
            if in_where_block and stripped_full and _leading_indent(raw) <= header_indent:
                break

        if not in_where_block:
            walrus = _top_level_walrus_index(raw)
            if walrus is not None:
                if include_body:
                    body_end = _peek_body_end(lines, offset, header_indent)
                    if body_end is not None:
                        # Include the `:=` line + all continuation lines
                        # through the body terminator.  Prior header lines
                        # (offsets `decl_index..offset-1`) are already in
                        # `collected` via earlier iterations of this loop.
                        for j in range(offset, body_end):
                            collected.append(lines[j].rstrip())
                        break
                # Cut just before `:=` — body is a long implementation or
                # this declaration kind hides bodies (theorem/lemma/example).
                before = raw[:walrus].rstrip()
                if before:
                    collected.append(before)
                break
        collected.append(raw)
        if not in_where_block and (
            stripped_full.endswith(" where") or stripped_full == "where"
        ):
            if not allow_where_block:
                # Signature ends at the `where` line — don't include the
                # proof/impl block body for theorems, lemmas, examples.
                break
            in_where_block = True
            # keep reading; don't break here anymore
            continue

    # Drop trailing blank lines but keep interior structure so multi-line
    # field docstrings stay readable.
    while collected and not collected[-1].strip():
        collected.pop()
    return "\n".join(collected).rstrip()


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
        # Track multi-line `/- ... -/` (including `/--` doc comments
        # and `/-!` module headers) so we don't try to extract
        # declaration names from lines inside a comment. Without this,
        # a phrase like "structure under convolution" in a prose
        # docstring would be mis-indexed as a Lean `structure`.
        in_block_comment = False

        for lineno, line in enumerate(lines, start=1):
            if in_block_comment:
                if "-/" in line:
                    in_block_comment = False
                continue
            stripped_line = line.lstrip()
            if stripped_line.startswith("/-"):
                # Block comment opens here. It may close on the same
                # line, in which case the matter is settled and we
                # carry on; otherwise we enter the block-comment state.
                rest = stripped_line[2:]
                if "-/" not in rest:
                    in_block_comment = True
                continue
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
            # Override semantics: when a declaration has its own
            # `Blueprint:` marker, that is the complete list and the
            # module-level `## Blueprint` section is ignored. The
            # module-level header only applies to declarations that
            # have no marker of their own. This is the right call
            # when a module backs multiple blueprint nodes — the
            # per-decl annotation overrides the module default rather
            # than unioning with it.
            if decl_blueprint:
                merged_nodes: list[str] = list(decl_blueprint)
            else:
                merged_nodes = list(module_blueprint_nodes)

            decl = LeanDeclaration(
                name=name,
                qualified_name=qualified,
                kind=keyword,
                file=lean_file,
                line=lineno,
                module=module,
                signature=_signature_snippet(lines, lineno - 1, keyword=keyword),
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
