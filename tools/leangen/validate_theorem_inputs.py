from __future__ import annotations

import argparse
import shutil
import tempfile
import sys
from pathlib import Path

from .common import module_name_from_path
from .lean_runner import build_module, run_lean_file


def _append_validation_probe(lean_path: Path, theorem_name: str) -> None:
    lean_path.write_text(
        lean_path.read_text(encoding="utf-8")
        + "\n"
        + f"""
run_cmd do
  let env : Lean.Environment ← Lean.getEnv
  let target := "{theorem_name}"
  let foundDecls := List.filter (fun (n, _) => n.toString == target) env.constants.toList
  match foundDecls with
  | [] =>
      IO.println "found=false"
  | (_, ci) :: _ =>
      let hasValue := (Lean.ConstantInfo.value? ci (allowOpaque := true)).isSome
      let depCount := match Lean.ConstantInfo.value? ci (allowOpaque := true) with
        | some v => (Lean.Expr.getUsedConstantsAsSet v).toArray.size
        | none => 0
      IO.println s!"found=true hasValue={{hasValue}} depCount={{depCount}}"
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leangen-validate-theorem-inputs")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--lean-file", required=True, type=Path)
    parser.add_argument("--theorem-name", required=True)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args(argv)

    module_name = module_name_from_path(args.source_root, args.lean_file)
    if not args.skip_build:
        build = build_module(project_root=args.project_root, module_name=module_name)
        if build.returncode != 0:
            raise SystemExit(build.returncode)

    with tempfile.TemporaryDirectory(prefix="leangen-validate-") as td:
        temp_root = Path(td) / args.source_root.name
        temp_lean = temp_root / args.lean_file.relative_to(args.source_root)
        temp_lean.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.lean_file, temp_lean)
        _append_validation_probe(temp_lean, args.theorem_name)
        run = run_lean_file(project_root=args.project_root, lean_file=temp_lean)
        if run.stdout:
            print(run.stdout, end="")
        if run.stderr:
            print(run.stderr, end="", file=sys.stderr)
        if run.returncode != 0:
            raise SystemExit(run.returncode)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
