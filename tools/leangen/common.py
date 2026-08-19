from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class TheoremRecord:
    name: str
    kind: str
    module: str
    type: str
    source_path: str
    range: dict | None = None


@dataclass(frozen=True)
class DependencyRecord:
    source: str
    target: str
    kind: str = "hard"
    module: str | None = None


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_to_dict(record) -> dict:
    return asdict(record)


def module_name_from_path(source_root: Path, lean_file: Path) -> str:
    rel = lean_file.resolve().relative_to(source_root.resolve())
    if rel.suffix == ".lean":
        rel = rel.with_suffix("")
    parts = list(rel.parts)
    if len(parts) == 1:
        parts.insert(0, source_root.name)
    return ".".join(parts)

