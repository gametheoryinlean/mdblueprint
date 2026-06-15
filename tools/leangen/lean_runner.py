from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess


@dataclass(frozen=True)
class LeanRun:
    returncode: int
    stdout: str
    stderr: str


def build_module(*, project_root: Path, module_name: str, lake_bin: str = "lake") -> LeanRun:
    cmd = [lake_bin, "build", module_name]
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )
    return LeanRun(proc.returncode, proc.stdout, proc.stderr)


def build_project(*, project_root: Path, lake_bin: str = "lake") -> LeanRun:
    cmd = [lake_bin, "build"]
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )
    return LeanRun(proc.returncode, proc.stdout, proc.stderr)


def run_lean_file(*, project_root: Path, lean_file: Path, lean_bin: str = "lean", lake_bin: str = "lake") -> LeanRun:
    cmd = [lake_bin, "env", lean_bin, str(lean_file)]
    proc = subprocess.run(
        cmd,
        cwd=project_root,
        env={**os.environ},
        text=True,
        capture_output=True,
        check=False,
    )
    return LeanRun(proc.returncode, proc.stdout, proc.stderr)

