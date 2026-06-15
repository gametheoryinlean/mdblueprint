from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import json
import re
from pathlib import Path
from typing import Iterable

from tools.knowledge.lean_countercheck import extract_decl_records


NAME_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_'])((?:[A-Za-z_][\w']*\.)*[A-Za-z_][\w']*)(?![A-Za-z0-9_'])")

STOPWORDS = {
    "a", "an", "and", "any", "at", "by", "cases", "constructor", "do", "exact",
    "exists", "false", "for", "fun", "have", "if", "intro", "is", "let", "match",
    "of", "on", "or", "proof", "right", "left", "rw", "simp", "simpa", "show",
    "subst", "then", "to", "with", "using", "by_cases", "by_contra", "rcases",
    "rename", "split", "specialize", "apply",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _looks_like_theorem_name(name: str) -> bool:
    if not name or len(name) <= 1:
        return False
    if name in STOPWORDS:
        return False
    if name.islower() and "." not in name and "_" not in name:
        return False
    return True


@lru_cache(maxsize=None)
def collect_corpus_names(source_root: str) -> tuple[str, ...]:
    root = Path(source_root).resolve()
    names: set[str] = set()
    for lean_file in sorted(root.rglob("*.lean")):
        if any(part in {'.git', '.lake', 'build', 'dist', 'node_modules', '__pycache__'} for part in lean_file.parts):
            continue
        try:
            for record in extract_decl_records(lean_file, root):
                names.add(record.name)
        except Exception:
            continue
    return tuple(sorted(names))


def _dependency_lookup(corpus_names: Iterable[str]) -> dict[str, set[str]]:
    lookup: dict[str, set[str]] = defaultdict(set)
    for name in corpus_names:
        if not _looks_like_theorem_name(name):
            continue
        base = name.split('.')[-1]
        for key in {name, _normalize_name(name), base, _normalize_name(base)}:
            if key:
                lookup[key].add(name)
    return lookup


def theorem_header(body: str) -> str:
    head = body.split(':=', 1)[0]
    head = head.split(' where', 1)[0]
    head = re.sub(r"\s+", " ", head).strip()
    return head


def _strip_comments(text: str) -> str:
    # Remove block and line comments before dependency token scanning.
    out: list[str] = []
    i = 0
    n = len(text)
    depth = 0
    while i < n:
        if depth == 0 and text.startswith('--', i):
            j = text.find('\n', i)
            if j == -1:
                break
            out.append('\n')
            i = j + 1
            continue
        if text.startswith('/-', i):
            depth += 1
            i += 2
            continue
        if depth > 0 and text.startswith('-/', i):
            depth -= 1
            i += 2
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return ''.join(out)


def _lookup_variants(token: str) -> list[str]:
    parts = token.split('.')
    variants = [token]
    # Prefer stripping method/projection suffixes such as `.mp`, `.mpr`, and
    # record the longest meaningful prefix first.
    for i in range(len(parts) - 1, 0, -1):
        variants.append('.'.join(parts[:i]))
    base = parts[-1]
    variants.append(base)
    return list(dict.fromkeys(variants))


def dependency_targets(body: str, corpus_names: Iterable[str], *, self_name: str | None = None) -> list[str]:
    lookup = _dependency_lookup(corpus_names)
    body = _strip_comments(body)
    targets: list[str] = []
    seen: set[str] = set()
    for match in NAME_TOKEN_RE.finditer(body):
        token = match.group(1)
        if self_name is not None and token == self_name:
            continue
        candidates = set()
        for variant in _lookup_variants(token):
            candidates.update(lookup.get(variant, set()))
            candidates.update(lookup.get(_normalize_name(variant), set()))
        for candidate in sorted(candidates, key=lambda s: (-len(s), s)):
            if candidate == self_name or candidate in seen:
                continue
            seen.add(candidate)
            targets.append(candidate)
    return targets


def theorem_records_for_file(lean_file: Path, source_root: Path) -> list[dict]:
    records = extract_decl_records(lean_file, source_root)
    corpus_names = collect_corpus_names(str(source_root))
    out: list[dict] = []
    for record in records:
        targets = dependency_targets(record.body, corpus_names, self_name=record.name)
        out.append(
            {
                'name': record.name,
                'kind': record.kind,
                'module': record.module,
                'type': theorem_header(record.body),
                'sourcePath': record.source_path,
                'range': None if record.line is None else {
                    'start': {'line': record.line, 'column': record.column},
                    'end': {'line': record.line, 'column': record.column},
                },
                'dependencies': targets,
            }
        )
    return out


def dependency_edges_for_file(lean_file: Path, source_root: Path, theorem_records: list[dict] | None = None) -> list[dict]:
    records = extract_decl_records(lean_file, source_root)
    corpus_names = collect_corpus_names(str(source_root))
    theorem_names = {record['name'] for record in theorem_records} if theorem_records is not None else {record.name for record in records}
    theorem_lookup = {record.name: record for record in records}
    deps: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for source in theorem_names:
        record = theorem_lookup.get(source)
        if record is None:
            continue
        targets = dependency_targets(record.body, corpus_names, self_name=record.name)
        for target in targets:
            key = (source, target, record.module)
            if key in seen:
                continue
            seen.add(key)
            deps.append({'source': source, 'target': target, 'kind': 'hard', 'module': record.module})
    return deps
