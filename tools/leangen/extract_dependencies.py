from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import module_name_from_path, write_json
from .text_extract import dependency_edges_for_file, theorem_records_for_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-extract-dependencies")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--lean-file", required=True, type=Path)
    parser.add_argument("--theorems-json", required=True, type=Path)
    parser.add_argument("--module-name", type=str)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    _ = args.project_root, args.skip_build
    theorem_records = json.loads(args.theorems_json.read_text(encoding="utf-8"))
    module_name = args.module_name or module_name_from_path(args.source_root, args.lean_file)
    deps = dependency_edges_for_file(args.lean_file, args.source_root, theorem_records=theorem_records)
    for dep in deps:
        dep["module"] = module_name
    write_json(args.output, deps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
