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


def _source_metadata(
    lean_file: Path,
    line: int,
    lean_root: Path,
    repository: LeanRepositoryConfig | None,
) -> dict[str, str | None]:
    if repository is None:
        return {
            "repository_id": None,
            "repository_title": None,
            "revision": None,
            "relative_path": None,
            "source_url": None,
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
    return {
        "repository_id": repository.id,
        "repository_title": repository.title,
        "revision": repository.revision,
        "relative_path": relative_path,
        "source_url": source_url,
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
                **_source_metadata(lean_file, lineno, lean_root, repository),
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
