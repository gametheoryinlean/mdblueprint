from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from .common import module_name_from_path
from .lean_runner import build_module, run_lean_file
from .templates import theorem_extraction_script


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-extract-theorems")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--lean-file", required=True, type=Path)
    parser.add_argument("--module-name", type=str)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    module_name = args.module_name or module_name_from_path(args.source_root, args.lean_file)
    if not args.skip_build:
        build = build_module(project_root=args.project_root, module_name=module_name)
        if build.returncode != 0:
            raise SystemExit(build.returncode)
    with tempfile.TemporaryDirectory(prefix="leangen-theorems-") as td:
        script = Path(td) / "extract_theorems.lean"
        script.write_text(theorem_extraction_script(module_name, args.output), encoding="utf-8")
        run = run_lean_file(project_root=args.project_root, lean_file=script)
        if run.returncode != 0:
            raise SystemExit(run.returncode)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

