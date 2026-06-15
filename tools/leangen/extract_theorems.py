from __future__ import annotations

import argparse
from pathlib import Path

from .common import module_name_from_path, write_json
from .text_extract import theorem_records_for_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-extract-theorems")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--lean-file", required=True, type=Path)
    parser.add_argument("--module-name", type=str)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    _ = args.project_root, args.skip_build
    module_name = args.module_name or module_name_from_path(args.source_root, args.lean_file)
    records = theorem_records_for_file(args.lean_file, args.source_root)
    for record in records:
        record["module"] = module_name
    write_json(args.output, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
