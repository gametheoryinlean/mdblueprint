from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from tools.knowledge.parser import parse_file


DECL_RE = re.compile(
    r"(?m)^(?:@[^\n]*\n\s*)*(?:theorem|lemma|def|abbrev|example)\s+"
    r"(?P<name>(?:[A-Za-z_][\w']*\.)*[A-Za-z_][\w']*)\b"
)


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


class LeanMCPClient:
    def __init__(self, project_root: Path, *, transport: str = "stdio") -> None:
        self.project_root = project_root.resolve()
        self.transport = transport
        self.proc: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._initialized = False

    def __enter__(self) -> "LeanMCPClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self.proc is not None:
            return
        if shutil.which("uvx") is None:
            raise RuntimeError("uvx not installed")
        env = os.environ.copy()
        env.setdefault("LEAN_PROJECT_PATH", str(self.project_root))
        env.setdefault("LEAN_LOG_LEVEL", "NONE")
        self.proc = subprocess.Popen(
            [
                "uvx",
                "lean-lsp-mcp",
                "--transport",
                self.transport,
                "--lean-project-path",
                str(self.project_root),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(self.project_root),
        )
        self._initialize()

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            self._send({"jsonrpc": "2.0", "method": "notifications/exit", "params": {}})
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def _initialize(self) -> None:
        self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mdblueprint-countercheck", "version": "0.1"},
            },
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._initialized = True

    def _send(self, message: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise RuntimeError("MCP process not started")
        data = json.dumps(message)
        payload = f"Content-Length: {len(data)}\r\n\r\n{data}"
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()

    def _read(self) -> dict[str, Any]:
        if self.proc is None or self.proc.stdout is None:
            raise RuntimeError("MCP process not started")
        headers: dict[str, str] = {}
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                raise RuntimeError("MCP server closed stdout")
            if line in ("\r\n", "\n"):
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.lower().strip()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = self.proc.stdout.read(length)
        if not body:
            raise RuntimeError("MCP response body missing")
        return json.loads(body)

    def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        while True:
            msg = self._read()
            if msg.get("id") != req_id:
                continue
            if "error" in msg:
                raise RuntimeError(f"MCP request failed: {msg['error']}")
            return msg.get("result")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._request("tools/call", {"name": name, "arguments": arguments})

    @staticmethod
    def _as_text(result: Any) -> str:
        if isinstance(result, dict):
            if isinstance(result.get("content"), list):
                parts: list[str] = []
                for chunk in result["content"]:
                    if isinstance(chunk, dict):
                        if isinstance(chunk.get("text"), str):
                            parts.append(chunk["text"])
                        elif isinstance(chunk.get("content"), str):
                            parts.append(chunk["content"])
                    elif isinstance(chunk, str):
                        parts.append(chunk)
                if parts:
                    return "\n".join(parts)
            if isinstance(result.get("text"), str):
                return result["text"]
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)


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


def _file_kind(line: str) -> str | None:
    stripped = line.lstrip()
    for kind in ("theorem", "lemma", "def", "abbrev", "example"):
        if stripped.startswith(kind + " "):
            return kind
    return None


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(m.end() for m in re.finditer(r"\n", text))
    return starts


def _position_of_offset(text: str, offset: int) -> tuple[int, int]:
    line_starts = _line_starts(text)
    line_no = 1
    for idx, start in enumerate(line_starts, start=1):
        if start > offset:
            break
        line_no = idx
    line_start = line_starts[line_no - 1]
    return line_no, offset - line_start + 1


def _offset_of_position(text: str, line: int, column: int) -> int:
    if line <= 0 or column <= 0:
        raise ValueError("line and column must be positive")
    line_starts = _line_starts(text)
    if line > len(line_starts):
        raise ValueError("line out of range")
    return line_starts[line - 1] + column - 1


def _parse_outline_items(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("declaration")
            kind = obj.get("kind") or obj.get("type")
            if isinstance(name, str) and isinstance(kind, str):
                rng = obj.get("range") or obj.get("span") or obj.get("location")
                items.append({"name": name, "kind": kind, "range": rng, "raw": obj})
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(payload)
    return items


def _range_start(rng: Any) -> tuple[int | None, int | None]:
    if isinstance(rng, dict):
        start = rng.get("start") or rng.get("from") or rng.get("begin")
        if isinstance(start, dict):
            line = start.get("line") or start.get("row")
            col = start.get("character") or start.get("column")
            if isinstance(line, int) and isinstance(col, int):
                return line, col
    return None, None


def extract_decl_records_mcp(lean_file: Path, source_root: Path, client: LeanMCPClient) -> list[DeclRecord]:
    text = _read_text(lean_file)
    rel_path = str(lean_file.resolve().relative_to(client.project_root)) if lean_file.resolve().is_relative_to(client.project_root) else str(lean_file)
    outline = client.call_tool("lean_file_outline", {"file_path": rel_path})
    outline_items = _parse_outline_items(outline)
    decls: list[tuple[str, str, int | None, int | None]] = []
    for item in outline_items:
        kind = item["kind"].lower()
        if not any(tok in kind for tok in ("theorem", "lemma", "def", "abbrev", "example", "structure", "class")):
            continue
        name = item["name"]
        line, col = _range_start(item.get("range"))
        decls.append((name, kind, line, col))
    if not decls:
        return extract_decl_records(lean_file, source_root)
    decls.sort(key=lambda x: ((x[2] or 10**9), (x[3] or 0), x[0]))
    offsets: list[int] = []
    for _name, _kind, line, col in decls:
        if line is None or col is None:
            offsets.append(-1)
        else:
            try:
                offsets.append(_offset_of_position(text, line, col))
            except Exception:
                offsets.append(-1)
    records: list[DeclRecord] = []
    for idx, (name, kind, line, col) in enumerate(decls):
        start = offsets[idx] if offsets[idx] >= 0 else text.find(name)
        if start < 0:
            continue
        end = next((off for off in offsets[idx + 1 :] if off >= 0), len(text))
        records.append(
            DeclRecord(
                name=name,
                kind=_file_kind(kind) or kind,
                module=_module_name(source_root, lean_file),
                source_path=str(lean_file),
                start=start,
                end=end,
                body=text[start:end],
                line=line,
                column=col,
            )
        )
    return records or extract_decl_records(lean_file, source_root)


def extract_decl_records(lean_file: Path, source_root: Path) -> list[DeclRecord]:
    text = _read_text(lean_file)
    module = _module_name(source_root, lean_file)
    matches = list(DECL_RE.finditer(text))
    records: list[DeclRecord] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        line_start = text.rfind("\n", 0, start) + 1
        line_no, col_no = _position_of_offset(text, start)
        kind = _file_kind(text[line_start:start]) or "theorem"
        records.append(
            DeclRecord(
                name=match.group("name"),
                kind=kind,
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


STOPWORDS = {
    "a", "an", "and", "any", "at", "by", "cases", "constructor", "do", "exact",
    "exists", "false", "for", "fun", "have", "if", "intro", "is", "let", "match",
    "of", "on", "or", "proof", "right", "left", "rw", "simp", "simpa", "show",
    "subst", "then", "to", "with", "using", "by_cases", "by_contra", "rcases",
    "rename", "split", "specialize", "apply",
}


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


def _names_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if _normalize_name(left) == _normalize_name(right):
        return True
    left_base = left.split(".")[-1]
    right_base = right.split(".")[-1]
    return _normalize_name(left_base) == _normalize_name(right_base)


def _iter_tool_names(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"####\s+([A-Za-z_][A-Za-z0-9_]+)", text):
        names.append(match.group(1))
    return names


def _proof_body_for_record(record: DeclRecord, text: str) -> str:
    return text[record.start : record.end]


def _references_in_span(text: str, candidate: str, start: int, end: int) -> bool:
    candidate_re = re.compile(rf"(?<![A-Za-z0-9_']){re.escape(candidate)}(?![A-Za-z0-9_'])")
    for match in candidate_re.finditer(text):
        if start <= match.start() < end:
            return True
    return False


def _reference_positions(payload: Any) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            line = obj.get("line") or obj.get("row")
            col = obj.get("column") or obj.get("character")
            if isinstance(line, int) and isinstance(col, int):
                positions.append((line, col))
            rng = obj.get("range") or obj.get("span") or obj.get("location")
            if isinstance(rng, dict):
                start = rng.get("start") or rng.get("from") or rng.get("begin")
                if isinstance(start, dict):
                    line = start.get("line") or start.get("row")
                    col = start.get("character") or start.get("column")
                    if isinstance(line, int) and isinstance(col, int):
                        positions.append((line, col))
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(payload)
    uniq: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for item in positions:
        if item in seen:
            continue
        seen.add(item)
        uniq.append(item)
    return uniq


def extract_dependency_edges(
    records: list[DeclRecord],
    corpus_names: set[str],
    restrict_to_same_file: bool = True,
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    current_names = {record.name for record in records}
    candidate_names = corpus_names & current_names if restrict_to_same_file else corpus_names
    candidate_names = {name for name in set(candidate_names) if _looks_like_theorem_name(name)}
    for record in records:
        body = record.body
        targets: list[str] = []
        for name in _longest_first(list(candidate_names - {record.name})):
            if re.search(rf"(?<![A-Za-z0-9_']){re.escape(name)}(?![A-Za-z0-9_'])", body):
                targets.append(name)
        for target in targets:
            edges.append({"source": record.name, "target": target, "kind": "hard", "module": record.module})
    return edges


def extract_dependency_edges_mcp(
    records: list[DeclRecord],
    client: LeanMCPClient,
    lean_file: Path,
    text: str,
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    rel_path = str(lean_file.resolve().relative_to(client.project_root)) if lean_file.resolve().is_relative_to(client.project_root) else str(lean_file)
    for source in records:
        if source.line is None or source.column is None:
            continue
        try:
            refs = client.call_tool(
                "lean_references",
                {"file_path": rel_path, "line": source.line, "column": max(source.column, 1)},
            )
        except Exception:
            continue
        for line, col in _reference_positions(refs):
            if line is None or col is None:
                continue
            try:
                ref_offset = _offset_of_position(text, line, col)
            except Exception:
                continue
            for target in records:
                if target.name == source.name:
                    continue
                if not (target.start <= ref_offset < target.end):
                    continue
                edges.append({"source": source.name, "target": target.name, "kind": "hard", "module": source.module})
                break
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


def _lean_lsp_mcp_probe() -> tuple[str, str]:
    if shutil.which("uvx") is None:
        return "unavailable", "uvx not installed"
    try:
        proc = subprocess.run(
            ["uvx", "lean-lsp-mcp", "--help"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return "unavailable", f"probe failed: {exc}"
    if proc.returncode == 0:
        return "available", "uvx lean-lsp-mcp --help succeeded"
    return "unavailable", (proc.stderr or proc.stdout or "lean-lsp-mcp probe failed").strip()


def build_countercheck_report(
    *,
    node_file: Path,
    lean_file: Path,
    source_root: Path,
    corpus_root: Path,
    method: str = "heuristic",
    compare_with_lsp: bool = True,
    lean_project_root: Path | None = None,
) -> CountercheckResult:
    node = _load_node(node_file)
    lean_project_root = (lean_project_root or corpus_root).resolve()
    text = _read_text(lean_file)
    corpus_names = build_name_corpus(corpus_root, source_root=source_root)
    method_status: dict[str, str] = {"heuristic": "used"}

    if method == "mcp":
        with LeanMCPClient(lean_project_root) as client:
            records = extract_decl_records_mcp(lean_file, source_root, client)
            extracted_edges = extract_dependency_edges_mcp(records, client, lean_file, text)
            method_status["lean-lsp-mcp"] = f"used: stdio client against {lean_project_root}"
    else:
        records = extract_decl_records(lean_file, source_root)
        extracted_names = [record.name for record in records]
        extracted_edges = extract_dependency_edges(records, corpus_names | set(extracted_names), restrict_to_same_file=False)
        if compare_with_lsp:
            status, note = _lean_lsp_mcp_probe()
            method_status["lean-lsp-mcp"] = f"{status}: {note}"

    extracted_names = [record.name for record in records]
    node_decls = list(node.lean.declarations) if node.lean else []
    node_uses = list(node.uses or [])
    matched = [decl for decl in node_decls if any(_names_match(decl, name) for name in extracted_names)]
    missing_decls = [decl for decl in node_decls if not any(_names_match(decl, name) for name in extracted_names)]
    extra_decls = [name for name in extracted_names if not any(_names_match(name, decl) for decl in node_decls)]

    extracted_targets = {edge["target"] for edge in extracted_edges}
    missing_uses = [use for use in node_uses if not any(_names_match(use, target) for target in extracted_targets)]
    extra_uses = [target for target in sorted(extracted_targets) if not any(_names_match(target, use) for use in node_uses)]

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
        "lean_project_root": str(lean_project_root),
        "method_status": method_status,
        "theorems": [dataclasses.asdict(record) for record in records],
        "dependencies": extracted_edges,
    }
    return CountercheckResult(
        node_id=node.id or node_file.stem,
        node_title=node.title or node_file.stem,
        node_declarations=node_decls,
        extracted_declarations=extracted_names,
        extracted_edges=extracted_edges,
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


def write_countercheck_report(report: CountercheckResult, reviews_dir: Path) -> Path:
    reviews_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    safe_ts = re.sub(r"[:+]", "_", timestamp)
    path = reviews_dir / f"{report.node_id.replace('.', '_')}_lean_countercheck_{safe_ts}.md"
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
    lines.extend([
        "",
        "## Matched Declarations",
        "",
    ])
    lines.extend(f"- `{decl}`" for decl in report.matched_declarations or ["(none)"])
    lines.extend([
        "",
        "## Missing Declarations",
        "",
    ])
    lines.extend(f"- `{decl}`" for decl in report.missing_declarations or ["(none)"])
    lines.extend([
        "",
        "## Extra Declarations",
        "",
    ])
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
    parser.add_argument("--lean-project-root", type=Path)
    parser.add_argument("--reviews-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-lsp-probe", action="store_true")
    parser.add_argument("--method", choices=("heuristic", "mcp"), default="heuristic")
    args = parser.parse_args(argv)

    report = build_countercheck_report(
        node_file=args.node_file,
        lean_file=args.lean_file,
        source_root=args.source_root,
        corpus_root=args.corpus_root,
        compare_with_lsp=not args.no_lsp_probe,
        lean_project_root=args.lean_project_root,
        method=args.method,
    )
    if args.output:
        args.output.write_text(json.dumps(report.raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.reviews_dir:
        report_path = write_countercheck_report(report, args.reviews_dir)
        print(report_path)
    else:
        print(json.dumps(report.raw, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
