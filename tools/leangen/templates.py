from __future__ import annotations

from pathlib import Path


def theorem_extraction_script(module_name: str, output_path: Path) -> str:
    return f"""import Lean
import Lean.Data.Json
import Lean.Util.FoldConsts
import {module_name}

open Lean
open Lean.Elab.Command

private def jsonArray (xs : List Json) : Json :=
  Json.arr xs.toArray

private def jsonStringArray (xs : List String) : Json :=
  jsonArray (xs.map Json.str)

private def keepDecl (n : Name) : Bool :=
  let s := n.toString
  !(s.startsWith "inst") && !(s.contains ".__proof_") && !(s.contains "._proof_")

private def declJson (moduleName : String) (sourcePath : String) (n : Name) (ci : ConstantInfo) : Json :=
  let deps := match ci.value? with
    | some v => v.getUsedConstantsAsSet.toList.map (fun d => d.toString)
    | none => []
  Json.mkObj [
    ("name", n.toString),
    ("kind", "theorem"),
    ("module", moduleName),
    ("type", toString ci.type),
    ("sourcePath", sourcePath),
    ("dependencies", jsonStringArray deps)
  ]

private def isTargetDecl (env : Environment) (targetModule : Name) (n : Name) : Bool :=
  match env.getModuleIdxFor? n, env.getModuleIdx? targetModule with
  | some a, some b => a == b
  | _, _ => false

run_cmd do
  let env ← getEnv
  let sourcePath := "{output_path.as_posix()}"
  let moduleName := "{module_name}"
  let targetModule : Name := `{module_name}
  let decls := env.constants.toList.filter fun (n, ci) => ci.isTheorem && keepDecl n && isTargetDecl env targetModule n
  let payload := jsonArray <| decls.map fun (n, ci) => declJson moduleName sourcePath n ci
  liftIO <| IO.FS.writeFile sourcePath (toString payload)
"""


def dependency_extraction_script(module_name: str, output_path: Path) -> str:
    return f"""import Lean
import Lean.Data.Json
import Lean.Util.FoldConsts
import {module_name}

open Lean
open Lean.Elab.Command

private def jsonArray (xs : List Json) : Json :=
  Json.arr xs.toArray

private def jsonStringArray (xs : List String) : Json :=
  jsonArray (xs.map Json.str)

private def isTargetDecl (env : Environment) (targetModule : Name) (n : Name) : Bool :=
  match env.getModuleIdxFor? n, env.getModuleIdx? targetModule with
  | some a, some b => a == b
  | _, _ => false

run_cmd do
  let env ← getEnv
  let moduleName := "{module_name}"
  let targetModule : Name := `{module_name}
  let outputPath := "{output_path.as_posix()}"
  let theoremDecls := env.constants.toList.filter fun (n, ci) => ci.isTheorem && keepDecl n && isTargetDecl env targetModule n
  let theoremNames := theoremDecls.map fun (n, _) => n
  let edges := theoremDecls.foldl (init := []) fun acc (sourceName, ci) =>
    let targets := match ci.value? with
      | some v => v.getUsedConstantsAsSet.toList.filter theoremNames.contains
      | none => []
    acc ++ targets.map fun targetName =>
      Json.mkObj [
        ("source", sourceName.toString),
        ("target", targetName.toString),
        ("kind", "hard"),
        ("module", moduleName)
      ]
  liftIO <| IO.FS.writeFile outputPath (toString (jsonArray edges))
"""
