from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from tools.knowledge.parser import parse_file


DECL_RE = re.compile(
    r"(?m)^(?:@[^\n]*\n\s*)*(?P<kind>theorem|lemma|def|abbrev|example)\s+"
    r"(?P<name>(?:[A-Za-z_][\w']*\.)*[A-Za-z_][\w']*)\b"
)


STOPWORDS = {
    "a", "an", "and", "any", "at", "by", "cases", "constructor", "do", "exact",
    "exists", "false", "for", "fun", "have", "if", "intro", "is", "let", "match",
    "of", "on", "or", "proof", "right", "left", "rw", "simp", "simpa", "show",
    "subst", "then", "to", "with", "using", "by_cases", "by_contra", "rcases",
    "rename", "split", "specialize", "apply",
}


@dataclasses.dataclass(frozen=True)
class DeclRecord:
    name: str
    kind: str
    module: str
    source_path: str
    start: int
    end: int
    body: str
    line: int | None = None
    column: int | None = None


@dataclasses.dataclass(frozen=True)
class CountercheckResult:
    node_id: str
    node_title: str
    node_declarations: list[str]
    extracted_declarations: list[str]
    extracted_edges: list[dict[str, str]]
    matched_declarations: list[str]
    missing_declarations: list[str]
    extra_declarations: list[str]
    node_uses: list[str]
    missing_uses: list[str]
    extra_uses: list[str]
    method_status: dict[str, str]
    sample_lean_file: str
    sample_node_file: str
    corpus_root: str
    raw: dict[str, Any]


def _module_name(source_root: Path, lean_file: Path) -> str:
    resolved = lean_file.resolve()
    try:
        rel = resolved.relative_to(source_root.resolve())
    except ValueError:
        return resolved.with_suffix("").name
    if rel.suffix == ".lean":
        rel = rel.with_suffix("")
    parts = list(rel.parts)
    if len(parts) == 1:
        parts.insert(0, source_root.name)
    return ".".join(parts)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(m.end() for m in re.finditer(r"\n", text))
    return starts


def _position_of_offset(text: str, offset: int) -> tuple[int, int]:
    starts = _line_starts(text)
    line_no = 1
    for idx, start in enumerate(starts, start=1):
        if start > offset:
            break
        line_no = idx
    line_start = starts[line_no - 1]
    return line_no, offset - line_start + 1


def extract_decl_records(lean_file: Path, source_root: Path) -> list[DeclRecord]:
    text = _read_text(lean_file)
    module = _module_name(source_root, lean_file)
    matches = list(DECL_RE.finditer(text))
    records: list[DeclRecord] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        line_no, col_no = _position_of_offset(text, start)
        records.append(
            DeclRecord(
                name=match.group("name"),
                kind=match.group("kind"),
                module=module,
                source_path=str(lean_file),
                start=start,
                end=end,
                body=text[start:end],
                line=line_no,
                column=col_no,
            )
        )
    return records


def build_name_corpus(corpus_root: Path, source_root: Path | None = None) -> set[str]:
    names: set[str] = set()
    if corpus_root.is_file():
        files = [corpus_root]
        source_root = source_root or corpus_root.parent
    else:
        files = sorted(corpus_root.rglob("*.lean"))
        source_root = source_root or corpus_root
    for lean_file in files:
        try:
            for record in extract_decl_records(lean_file, source_root):
                names.add(record.name)
        except Exception:
            try:
                fallback_root = lean_file.parent
                for record in extract_decl_records(lean_file, fallback_root):
                    names.add(record.name)
            except Exception:
                continue
    return names


def _longest_first(candidates: list[str]) -> list[str]:
    return sorted(set(candidates), key=lambda s: (-len(s), s))


def _looks_like_theorem_name(name: str) -> bool:
    if not name or len(name) <= 1:
        return False
    if name in STOPWORDS:
        return False
    if name.islower() and "." not in name and "_" not in name:
        return False
    return True


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def safe_countercheck_artifact_stem(node_id: str, lean_file: Path | str, module: str | None = None) -> str:
    """Build a stable per-node/per-Lean-module stem for countercheck artifacts."""
    node_slug = re.sub(r"[^A-Za-z0-9]+", "_", node_id).strip("_") or "node"
    module_source = module or Path(lean_file).with_suffix("").name
    module_slug = re.sub(r"[^A-Za-z0-9]+", "_", module_source).strip("_") or "lean"
    return f"{node_slug}__{module_slug}"


def _names_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if _normalize_name(left) == _normalize_name(right):
        return True
    left_base = left.split(".")[-1]
    right_base = right.split(".")[-1]
    return _normalize_name(left_base) == _normalize_name(right_base)


def _declarations_match(left: str, right: str) -> bool:
    """Match authored Lean declarations without basename-only collisions."""
    return left == right or _normalize_name(left) == _normalize_name(right)


def extract_dependency_edges(records: list[DeclRecord], corpus_names: set[str]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    current_names = {record.name for record in records}
    candidate_names = {name for name in corpus_names & current_names if _looks_like_theorem_name(name)}
    for record in records:
        for name in _longest_first(list(candidate_names - {record.name})):
            if re.search(rf"(?<![A-Za-z0-9_']){re.escape(name)}(?![A-Za-z0-9_'])", record.body):
                edges.append({"source": record.name, "target": name, "kind": "hard", "module": record.module})
    uniq: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge["source"], edge["target"], edge["module"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(edge)
    return uniq


def _load_node(node_file: Path):
    return parse_file(node_file)


def build_countercheck_report(
    *,
    node_file: Path,
    lean_file: Path,
    source_root: Path,
    corpus_root: Path,
    corpus_names: set[str] | None = None,
    method: str = "heuristic",
) -> CountercheckResult:
    _ = method
    node = _load_node(node_file)
    records = extract_decl_records(lean_file, source_root)
    extracted_names = [record.name for record in records]
    if corpus_names is None:
        corpus_names = build_name_corpus(corpus_root, source_root=source_root)
    edges = extract_dependency_edges(records, corpus_names | set(extracted_names))

    node_decls = list(node.lean.declarations) if node.lean else []
    node_uses = list(node.uses or [])
    matched = [decl for decl in node_decls if any(_declarations_match(decl, name) for name in extracted_names)]
    missing_decls = [decl for decl in node_decls if not any(_declarations_match(decl, name) for name in extracted_names)]
    extra_decls = [name for name in extracted_names if not any(_declarations_match(name, decl) for decl in node_decls)]

    extracted_targets = {edge["target"] for edge in edges}
    missing_uses = (
        [use for use in node_uses if not any(_names_match(use, target) for target in extracted_targets)]
        if extracted_targets else []
    )
    extra_uses = [target for target in sorted(extracted_targets) if not any(_names_match(target, use) for use in node_uses)]

    method_status: dict[str, str] = {"heuristic": "used"}
    raw = {
        "node": {
            "id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
            "uses": list(node.uses),
            "lean": {
                "repository": node.lean.repository if node.lean else None,
                "modules": list(node.lean.modules) if node.lean else [],
                "declarations": list(node.lean.declarations) if node.lean else [],
            },
            "tags": list(node.tags),
            "body": node.body,
            "file_path": str(node.file_path) if node.file_path else None,
        },
        "lean_file": str(lean_file),
        "source_root": str(source_root),
        "corpus_root": str(corpus_root),
        "method_status": method_status,
        "theorems": [dataclasses.asdict(record) for record in records],
        "dependencies": edges,
    }
    return CountercheckResult(
        node_id=node.id or node_file.stem,
        node_title=node.title or node_file.stem,
        node_declarations=node_decls,
        extracted_declarations=extracted_names,
        extracted_edges=edges,
        matched_declarations=matched,
        missing_declarations=missing_decls,
        extra_declarations=extra_decls,
        node_uses=node_uses,
        missing_uses=missing_uses,
        extra_uses=extra_uses,
        method_status=method_status,
        sample_lean_file=str(lean_file),
        sample_node_file=str(node_file),
        corpus_root=str(corpus_root),
        raw=raw,
    )


def write_countercheck_report(
    report: CountercheckResult,
    reviews_dir: Path,
    *,
    filename_stem: str | None = None,
) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    safe_ts = re.sub(r"[:+]", "_", timestamp)
    stem = filename_stem or f"{report.node_id.replace('.', '_')}_lean_countercheck"
    path = reviews_dir / f"{stem}_{safe_ts}.md"
    lines = [
        "---",
        "agent: lean-countercheck",
        f"node_id: {report.node_id}",
        f'created_at: "{timestamp}"',
        "---",
        "",
        f"# Lean Countercheck: {report.node_title}",
        "",
        "## Inputs",
        "",
        f"- node file: `{report.sample_node_file}`",
        f"- lean file: `{report.sample_lean_file}`",
        f"- corpus root: `{report.corpus_root}`",
        "",
        "## Method Status",
        "",
    ]
    for method, status in report.method_status.items():
        lines.append(f"- {method}: {status}")
    lines.extend(["", "## Matched Declarations", ""])
    lines.extend(f"- `{decl}`" for decl in report.matched_declarations or ["(none)"])
    lines.extend(["", "## Missing Declarations", ""])
    lines.extend(f"- `{decl}`" for decl in report.missing_declarations or ["(none)"])
    lines.extend(["", "## Extra Declarations", ""])
    lines.extend(f"- `{decl}`" for decl in report.extra_declarations or ["(none)"])
    lines.extend([
        "",
        "## Node Uses vs Extracted Dependencies",
        "",
        f"- node uses: {', '.join(f'`{u}`' for u in report.node_uses) or '(none)'}",
        f"- missing uses: {', '.join(f'`{u}`' for u in report.missing_uses) or '(none)'}",
        f"- extra uses: {', '.join(f'`{u}`' for u in report.extra_uses) or '(none)'}",
        "",
        "## Raw Snapshot",
        "",
        "```json",
        json.dumps(report.raw, indent=2, sort_keys=True),
        "```",
        "",
        "## Intent",
        "",
        "- Lean is acting as a counterchecker only.",
        "- Blank or flawed proofs are recorded as incompleteness, not inconsistency.",
        "- Any new lemmata discovered here are proposals for review, not automatic edits.",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mdblueprint-lean-countercheck")
    parser.add_argument("--node-file", required=True, type=Path)
    parser.add_argument("--lean-file", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--reviews-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_countercheck_report(
        node_file=args.node_file,
        lean_file=args.lean_file,
        source_root=args.source_root,
        corpus_root=args.corpus_root,
    )
    if args.output:
        args.output.write_text(json.dumps(report.raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.reviews_dir:
        print(write_countercheck_report(report, args.reviews_dir))
    else:
        print(json.dumps(report.raw, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
