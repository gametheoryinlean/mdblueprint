from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
import tempfile

from .common import module_name_from_path
from .lean_runner import build_module, run_lean_file


def _lean_string(value: str) -> str:
    return json.dumps(value)


def _dependency_probe(theorem_names: list[str]) -> str:
    names = ", ".join(_lean_string(name) for name in theorem_names)
    return f"""

run_cmd do
  let env : Lean.Environment <- Lean.getEnv
  let theoremNames : List String := [{names}]
  let theoremDecls : List (Lean.Name × Lean.ConstantInfo) :=
    env.constants.toList.filter fun (n, ci) =>
      ci.isTheorem && theoremNames.contains n.toString
  let edges := theoremDecls.foldl (init := []) fun acc (sourceName, ci) =>
    let targets := match Lean.ConstantInfo.value? ci (allowOpaque := true) with
      | some v =>
          (Lean.Expr.getUsedConstantsAsSet v).toArray.toList.filter fun (targetName : Lean.Name) =>
            theoremNames.contains targetName.toString
      | none => []
    acc ++ targets.map fun (targetName : Lean.Name) =>
      (sourceName.toString, targetName.toString)
  for (source, target) in edges do
    IO.println (source ++ "\t" ++ target)
"""


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

    theorem_records = json.loads(args.theorems_json.read_text(encoding="utf-8"))
    theorem_names = [record["name"] for record in theorem_records]
    module_name = args.module_name or module_name_from_path(args.source_root, args.lean_file)
    if not args.skip_build:
        build = build_module(project_root=args.project_root, module_name=module_name)
        if build.returncode != 0:
            if build.stdout:
                print(build.stdout)
            if build.stderr:
                print(build.stderr)
            raise SystemExit(build.returncode)
    with tempfile.TemporaryDirectory(prefix="leangen-deps-") as td:
        temp_root = Path(td) / args.source_root.name
        temp_lean = temp_root / args.lean_file.relative_to(args.source_root)
        temp_lean.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.lean_file, temp_lean)
        temp_lean.write_text(
            "import Lean.Elab.Command\nimport Lean.Util.FoldConsts\n"
            + temp_lean.read_text(encoding="utf-8")
            + _dependency_probe(theorem_names),
            encoding="utf-8",
        )
        run = run_lean_file(project_root=args.project_root, lean_file=temp_lean)
        if run.returncode != 0:
            if run.stdout:
                print(run.stdout)
            if run.stderr:
                print(run.stderr)
            raise SystemExit(run.returncode)
        deps = []
        for line in run.stdout.splitlines():
            if "	" not in line:
                continue
            source, target = line.split("	", 1)
            deps.append({
                "source": source,
                "target": target,
                "kind": "hard",
                "module": module_name,
            })
        args.output.write_text(
            json.dumps(deps, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
