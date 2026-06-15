from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .lean_runner import build_project, run_lean_file


def _lean_string(value: str) -> str:
    return json.dumps(value)


def _lean_name(module_name: str) -> str:
    return '`' + module_name


def _project_script(modules: list[tuple[str, str]], theorem_output: Path, dependency_output: Path) -> str:
    module_entries = ",\n    ".join(
        f"({_lean_name(module)}, {_lean_string(path)})" for module, path in modules
    )
    return f"""import Lean
import Lean.Data.Json
import Lean.Elab.Command
import Lean.Util.FoldConsts
import EconCSLib

open Lean
open Lean.Elab.Command

private def jsonArray (xs : List Json) : Json :=
  Json.arr xs.toArray

private def jsonStringArray (xs : List String) : Json :=
  jsonArray (xs.map Json.str)

private def keepDecl (n : Name) : Bool :=
  let s := n.toString
  !(s.startsWith "inst") && !(s.contains ".__proof_") && !(s.contains "._proof_")

private def targetModules : List (Name × String) := [
    {module_entries}
  ]

private def moduleInfoForDecl? (env : Environment) (n : Name) : Option (String × String) := do
  let declIdx ← env.getModuleIdxFor? n
  let (moduleName, sourcePath) ← targetModules.find? fun (m, _) =>
    match env.getModuleIdx? m with
    | some moduleIdx => moduleIdx == declIdx
    | none => false
  some (moduleName.toString, sourcePath)

private def declJson (env : Environment) (n : Name) (ci : ConstantInfo) (moduleName : String) (sourcePath : String) : Json :=
  let deps := match Lean.ConstantInfo.value? ci (allowOpaque := true) with
    | some v => (Lean.Expr.getUsedConstantsAsSet v).toArray.toList.map (fun d => d.toString)
    | none => []
  Json.mkObj [
    ("name", n.toString),
    ("kind", "theorem"),
    ("module", moduleName),
    ("type", toString ci.type),
    ("sourcePath", sourcePath),
    ("dependencies", jsonStringArray deps)
  ]

run_cmd do
  let env ← getEnv
  let theoremDecls : List (Name × ConstantInfo × String × String) :=
    env.constants.toList.filterMap fun (n, ci) =>
      if ci.isTheorem && keepDecl n then
        match moduleInfoForDecl? env n with
        | some (moduleName, sourcePath) => some (n, ci, moduleName, sourcePath)
        | none => none
      else
        none
  let theoremNames := theoremDecls.map fun (n, _, _, _) => n
  let theoremPayload := jsonArray <| theoremDecls.map fun (n, ci, moduleName, sourcePath) =>
    declJson env n ci moduleName sourcePath
  let edgePayload := theoremDecls.foldl (init := []) fun acc (sourceName, ci, moduleName, _) =>
    let targets := match Lean.ConstantInfo.value? ci (allowOpaque := true) with
      | some v =>
          (Lean.Expr.getUsedConstantsAsSet v).toArray.toList.filter fun (targetName : Name) =>
            theoremNames.contains targetName
      | none => []
    acc ++ targets.map fun (targetName : Name) =>
      Json.mkObj [
        ("source", sourceName.toString),
        ("target", targetName.toString),
        ("kind", "hard"),
        ("module", moduleName)
      ]
  liftIO <| IO.FS.writeFile {_lean_string(theorem_output.as_posix())} (toString theoremPayload)
  liftIO <| IO.FS.writeFile {_lean_string(dependency_output.as_posix())} (toString (jsonArray edgePayload))
"""


def _is_ignored(path: Path) -> bool:
    parts = set(path.parts)
    return any(part in parts for part in {'.git', '.lake', 'build', 'dist', 'node_modules', '__pycache__'})


def _module_name_from_source(source_root: Path, lean_file: Path) -> str:
    rel = lean_file.resolve().relative_to(source_root.resolve())
    if rel.suffix == '.lean':
        rel = rel.with_suffix('')
    return '.'.join(rel.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='leangen-extract-project')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--theorems-output', required=True, type=Path)
    parser.add_argument('--dependencies-output', required=True, type=Path)
    parser.add_argument('--skip-build', action='store_true')
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    source_root = (args.source_root or project_root).resolve()
    lean_files = [
        p for p in sorted(source_root.rglob('*.lean'))
        if not _is_ignored(p.relative_to(source_root))
    ]
    modules = [(_module_name_from_source(source_root, p), p.relative_to(source_root).as_posix()) for p in lean_files]

    if not args.skip_build:
        build = build_project(project_root=project_root)
        if build.returncode != 0:
            if build.stdout:
                print(build.stdout)
            if build.stderr:
                print(build.stderr)
            raise SystemExit(build.returncode)

    args.theorems_output.parent.mkdir(parents=True, exist_ok=True)
    args.dependencies_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='leangen-project-') as td:
        script = Path(td) / 'extract_project.lean'
        script.write_text(_project_script(modules, args.theorems_output, args.dependencies_output), encoding='utf-8')
        run = run_lean_file(project_root=project_root, lean_file=script)
        if run.returncode != 0:
            if run.stdout:
                print(run.stdout)
            if run.stderr:
                print(run.stderr)
            raise SystemExit(run.returncode)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
