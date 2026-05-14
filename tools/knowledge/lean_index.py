"""Extract Lean 4 declarations from source files into an index."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


DECL_KEYWORDS = re.compile(
    r"^(def|theorem|lemma|abbrev|instance|structure|class|inductive|"
    r"noncomputable def|noncomputable instance|"
    r"protected def|protected theorem|protected lemma|"
    r"private def|private theorem|private lemma)\s+",
    re.MULTILINE,
)

SORRY_RE = re.compile(r"\bsorry\b")
ADMIT_RE = re.compile(r"\badmit\b")
NAMESPACE_RE = re.compile(r"^namespace\s+(\S+)", re.MULTILINE)
END_NAMESPACE_RE = re.compile(r"^end\s+(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class LeanDeclaration:
    name: str
    qualified_name: str
    kind: str
    file: Path
    line: int
    has_sorry: bool = False


@dataclass
class LeanIndex:
    declarations: dict[str, LeanDeclaration] = field(default_factory=dict)
    sorry_decls: list[str] = field(default_factory=list)
    modules: dict[str, Path] = field(default_factory=dict)


def _extract_decl_name(line: str) -> tuple[str, str] | None:
    m = DECL_KEYWORDS.match(line.lstrip())
    if m is None:
        return None
    keyword = m.group(1)
    rest = line.lstrip()[m.end():]
    # Extract the name (up to space, colon, open brace/paren, or where)
    name_match = re.match(r"[{(\[].*?[})\]]\s*", rest)
    if name_match:
        rest = rest[name_match.end():]
    name_match = re.match(r"(\S+)", rest)
    if name_match is None:
        return None
    name = name_match.group(1).rstrip(":")
    # Strip implicit parameters from the name
    if "{" in name or "(" in name or "[" in name:
        return None
    return keyword, name


def _module_name(file: Path, lean_root: Path) -> str:
    rel = file.relative_to(lean_root)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def index_lean_project(lean_root: Path) -> LeanIndex:
    idx = LeanIndex()

    for lean_file in sorted(lean_root.rglob("*.lean")):
        module = _module_name(lean_file, lean_root)
        idx.modules[module] = lean_file

        lines = lean_file.read_text(encoding="utf-8").splitlines()
        namespace_stack: list[str] = []

        for lineno, line in enumerate(lines, start=1):
            # Track namespaces
            ns_match = NAMESPACE_RE.match(line)
            if ns_match:
                namespace_stack.append(ns_match.group(1))
                continue
            end_match = END_NAMESPACE_RE.match(line)
            if end_match:
                if namespace_stack and namespace_stack[-1] == end_match.group(1):
                    namespace_stack.pop()
                continue

            result = _extract_decl_name(line)
            if result is None:
                continue
            keyword, name = result

            prefix = ".".join(namespace_stack)
            qualified = f"{prefix}.{name}" if prefix else name

            # Check for sorry in the declaration body (rough heuristic: next 50 lines)
            body_text = "\n".join(lines[lineno - 1:lineno + 50])
            has_sorry = bool(SORRY_RE.search(body_text)) or bool(ADMIT_RE.search(body_text))

            decl = LeanDeclaration(
                name=name,
                qualified_name=qualified,
                kind=keyword,
                file=lean_file,
                line=lineno,
                has_sorry=has_sorry,
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
