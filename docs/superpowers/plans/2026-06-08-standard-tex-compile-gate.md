# Standard-TeX Compile Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan task-by-task in the current session, dispatching each task's TDD loop and reviewing at the checkpoints between tasks.

**Goal:** Add an opt-in, flag-gated "收口 gate" that projects a node's Markdown body into standard LaTeX and compiles it with `lualatex` under a shared preamble. Compile success means the node's math/TeX content is valid, standard, compilable LaTeX; compile failure produces one rejectable `TEX-COMPILE` diagnostic. The gate skips gracefully (returns `[]`) when `lualatex` is absent so CI without TeX is unaffected.

**Architecture:** Two new pure-ish modules plus wiring. `tex_projector.py` deterministically turns a `Node` into a minimal compilable `article` document (extract math spans via the existing `TEX_MATH_RE`, emit a fixed preamble + one zero-arg `\newcommand` per declared macro, discard prose). `tex_compile_check.py` runs that projection through `lualatex` in a `TemporaryDirectory` and parses the first `! `-prefixed error into a `Diagnostic(code="TEX-COMPILE")`. Both `check.py` (per-node CLI path) and `admission_pipeline.py` (staged-node admission path) gain an opt-in `strict_tex_compile` flag that runs the gate.

**Tech Stack:** Python 3.12+, stdlib `re`/`shutil`/`subprocess`/`tempfile`, pytest (flat `tests/`, `tmp_path`), `lualatex` (TeX Live), `uv` for the dev environment.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `tools/knowledge/tex_projector.py` | Create | `project_node_to_latex(node, *, macros)` — deterministic Node→standard-LaTeX `article` string |
| `tools/knowledge/tex_compile_check.py` | Create | `check_node_tex_compile(node, *, declared_macros, lualatex_bin)` — project + compile + diagnose |
| `tools/knowledge/check.py` | Modify | Add `strict_tex_compile` param + `--strict-tex-compile` CLI flag; call gate after `check_node_math` |
| `tools/knowledge/admission_pipeline.py` | Modify | Add opt-in `("tex_compile", ...)` gate + `strict_tex_compile` param; load macros via `load_project_config` |
| `tests/test_tex_projector.py` | Create | Unit tests for the projector |
| `tests/test_tex_compile_check.py` | Create | Unit tests for the compile gate (skip when `lualatex` absent) |
| `tests/test_check.py` | Modify | Add a `--strict-tex-compile` CLI integration test |
| `tests/test_admission_pipeline.py` | Modify | Add a `strict_tex_compile` gate test |

Verified facts used by this plan (re-confirmed against current source):
- `tools/knowledge/renderer.py` line 51 defines `TEX_MATH_RE` (a single `re.compile` with **no named groups**; alternation order is `$$..$$`, `\[..\]`, `\(..\)`, `$..$`). Each match's `group(0)` is the full delimited span **including** its delimiters.
- `tools/knowledge/validator.py` line 34 `@dataclass Diagnostic`: `level: str`, `node_id: str`, `message: str`, `file_path: Path | None = None`, `code: str | None = None`, `related: tuple[str, ...] = ()`.
- `tools/knowledge/latex_check.py` line 171 `check_node_math(node, *, declared_macros: Collection[str] | None = None) -> list[Diagnostic]`.
- `tools/knowledge/models.py`: `Node` has `id: str` (line 112), `body: str = ""` (line 127), `file_path: Path | None = None` (line 128). `parse_file(path) -> Node` exists.
- `tools/knowledge/config.py`: `MathConfig.macros: dict[str, str]` (name-without-backslash → expansion, line 38); `load_project_config(knowledge_root, config_path=None) -> ProjectConfig` (line 535). `check.py` obtains macros via `set(config.math.macros)` (line 51).
- `tools/knowledge/check.py` line 25 `check_knowledge_base(root, *, lean_root=None, config_path=None, strict_lean_git=False, strict_lean_placeholders=False)`; `main()` defines `--strict-lean-git`/`--strict-lean-placeholders` as `action="store_true"`.
- `tools/knowledge/admission_pipeline.py` line 54 `_gate(name, diags)` helper; line 152 `run_admission_pipeline(staged_path, knowledge_root, *, require_reviews=True, dry_run=False)`; `gate_checks` list at line 162; gate order is `schema, generality, verification, reviews, dag, write`.
- Tests: flat `tests/`, pytest, `tmp_path`. CLI tests shell out via `subprocess.run([sys.executable, "-m", "tools.knowledge.check", ...], capture_output=True, text=True)`. `tests/test_latex_check.py` has a `_write_node(path, *, node_id, body)` helper. There is **no** existing binary-skip pattern — this plan introduces one.
- Binaries present on the dev machine: `lualatex` at `/Library/TeX/texbin/lualatex`. CI Ubuntu has no TeX.

Test runner command used throughout: `uv run --extra dev python -m pytest <args>` from the repo root `/Users/hoxide/mycodes/mdblueprint`.

---

## Task 1: Projector — `project_node_to_latex`

**Files:**
- Create: `tools/knowledge/tex_projector.py`
- Test: `tests/test_tex_projector.py`

The projector extracts every math span from `node.body` using `TEX_MATH_RE`, re-emits each span in canonical form (display spans `\[..\]`/`$$..$$` → `\[ ... \]`; inline spans `\(..\)`/`$..$` → `$ ... $`), discards all prose, and wraps the result in a fixed preamble. Each declared macro becomes one zero-argument `\newcommand{\name}{expansion}` (the zero-arg limitation is a documented known constraint).

- [ ] Write failing test file `tests/test_tex_projector.py`:

```python
"""Unit tests for the Node -> standard-LaTeX projector."""
from __future__ import annotations

import textwrap
from pathlib import Path

from tools.knowledge.models import Node
from tools.knowledge.tex_projector import project_node_to_latex


def _node(body: str) -> Node:
    return Node(
        id="math.sample",
        title="Sample",
        kind="theorem",
        status="admitted",
        body=textwrap.dedent(body).strip(),
        file_path=Path("sample.md"),
    )


def test_preamble_is_present_and_standard():
    latex = project_node_to_latex(_node(r"Prose then $x = 1$ done."), macros={})
    assert r"\documentclass{article}" in latex
    assert r"\usepackage{amsmath,amssymb,amsthm}" in latex
    assert r"\usepackage{tikz}" in latex
    assert r"\usetikzlibrary{cd}" in latex
    assert r"\begin{document}" in latex
    assert r"\end{document}" in latex


def test_inline_span_is_emitted_as_dollar_math():
    latex = project_node_to_latex(_node(r"Let $x = 1$ here."), macros={})
    assert "$ x = 1 $" in latex
    # Prose is discarded: the surrounding words must not appear in the body.
    body = latex.split(r"\begin{document}", 1)[1]
    assert "Let" not in body
    assert "here" not in body


def test_display_span_is_emitted_as_bracket_math():
    latex = project_node_to_latex(_node(r"\[ a^2 + b^2 = c^2 \]"), macros={})
    assert r"\[ a^2 + b^2 = c^2 \]" in latex


def test_dollar_dollar_span_becomes_bracket_display():
    latex = project_node_to_latex(_node("$$ E = mc^2 $$"), macros={})
    assert r"\[ E = mc^2 \]" in latex


def test_paren_inline_span_becomes_dollar_inline():
    latex = project_node_to_latex(_node(r"\( y = 2 \)"), macros={})
    assert "$ y = 2 $" in latex


def test_macros_become_zero_arg_newcommands():
    latex = project_node_to_latex(
        _node(r"$\GG$"), macros={"GG": r"\mathbb{G}", "RR": r"\mathbb{R}"}
    )
    assert r"\newcommand{\GG}{\mathbb{G}}" in latex
    assert r"\newcommand{\RR}{\mathbb{R}}" in latex
    # Macros are declared before \begin{document}.
    preamble = latex.split(r"\begin{document}", 1)[0]
    assert r"\newcommand{\GG}{\mathbb{G}}" in preamble


def test_node_without_math_yields_empty_body_but_valid_doc():
    latex = project_node_to_latex(_node("Just prose, no math at all."), macros={})
    assert r"\begin{document}" in latex
    assert r"\end{document}" in latex
    body = latex.split(r"\begin{document}", 1)[1].split(r"\end{document}", 1)[0]
    assert body.strip() == ""
```

- [ ] Run it; expect **FAIL** (`ModuleNotFoundError: tools.knowledge.tex_projector`):

```
uv run --extra dev python -m pytest tests/test_tex_projector.py
```

- [ ] Create `tools/knowledge/tex_projector.py` with the full implementation:

```python
"""Deterministic projection of a node's Markdown body into standard LaTeX.

The projector extracts every math span from ``node.body`` using the same
``TEX_MATH_RE`` the renderer uses, re-emits each span in canonical form, and
wraps the result in a fixed, compilable ``article`` preamble. Prose is
discarded entirely: only the validity of the math/TeX content matters for the
compile gate.

Known constraint: declared macros are emitted as **zero-argument**
``\\newcommand`` forms. Macros that take arguments are not yet supported; macro
arity inference is deferred to a later plan.
"""
from __future__ import annotations

from tools.knowledge.models import Node
from tools.knowledge.renderer import TEX_MATH_RE

_PREAMBLE_HEAD = "\n".join(
    [
        r"\documentclass{article}",
        r"\usepackage{amsmath,amssymb,amsthm}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{cd}",
    ]
)


def _newcommands(macros: dict[str, str]) -> str:
    lines = [
        rf"\newcommand{{\{name}}}{{{expansion}}}"
        for name, expansion in macros.items()
    ]
    return "\n".join(lines)


def _canonical_span(span: str) -> str:
    """Re-emit one matched math span in canonical inline/display form.

    ``span`` is a full ``TEX_MATH_RE`` match including its delimiters. Display
    spans (``\\[..\\]`` and ``$$..$$``) become ``\\[ ... \\]``; inline spans
    (``\\(..\\)`` and ``$..$``) become ``$ ... $``.
    """
    if span.startswith("$$") and span.endswith("$$"):
        inner = span[2:-2].strip()
        return rf"\[ {inner} \]"
    if span.startswith(r"\[") and span.endswith(r"\]"):
        inner = span[2:-2].strip()
        return rf"\[ {inner} \]"
    if span.startswith(r"\(") and span.endswith(r"\)"):
        inner = span[2:-2].strip()
        return rf"$ {inner} $"
    # Remaining case: a single-dollar inline span ``$..$``.
    inner = span[1:-1].strip()
    return rf"$ {inner} $"


def project_node_to_latex(node: Node, *, macros: dict[str, str]) -> str:
    """Project a node's body into a minimal compilable standard-LaTeX document.

    Only math spans are kept; prose is discarded. Each declared macro becomes a
    zero-argument ``\\newcommand`` in the preamble (see module docstring for the
    arity limitation).
    """
    spans = [_canonical_span(m.group(0)) for m in TEX_MATH_RE.finditer(node.body)]
    body = "\n\n".join(spans)

    preamble_parts = [_PREAMBLE_HEAD]
    newcommands = _newcommands(macros)
    if newcommands:
        preamble_parts.append(newcommands)

    return "\n".join(
        [
            *preamble_parts,
            r"\begin{document}",
            body,
            r"\end{document}",
            "",
        ]
    )
```

- [ ] Run it; expect **PASS**:

```
uv run --extra dev python -m pytest tests/test_tex_projector.py
```

- [ ] Commit (new files must be `git add`ed — `-am` alone would miss untracked files):

```
git add tools/knowledge/tex_projector.py tests/test_tex_projector.py
git commit -m "feat(knowledge): add Node->standard-LaTeX projector for compile gate"
```

---

## Task 2: Compile gate — `check_node_tex_compile`

**Files:**
- Create: `tools/knowledge/tex_compile_check.py`
- Test: `tests/test_tex_compile_check.py`

This module projects the node, writes the LaTeX to a `TemporaryDirectory`, runs `lualatex` non-interactively, and on failure parses the first `! `-prefixed line from stdout (TeX's standard error-line marker) into a single `Diagnostic`. If `lualatex` is unavailable it returns `[]` (graceful skip). The tests introduce a reusable `requires_lualatex` skip marker.

- [ ] Write failing test file `tests/test_tex_compile_check.py`:

```python
"""Unit tests for the lualatex compile gate."""
from __future__ import annotations

import shutil
import textwrap
from pathlib import Path

import pytest

from tools.knowledge.models import Node
from tools.knowledge.tex_compile_check import check_node_tex_compile

requires_lualatex = pytest.mark.skipif(
    shutil.which("lualatex") is None,
    reason="lualatex not installed; compile gate skips gracefully",
)


def _node(node_id: str, body: str) -> Node:
    return Node(
        id=node_id,
        title="Sample",
        kind="theorem",
        status="admitted",
        body=textwrap.dedent(body).strip(),
        file_path=Path(f"{node_id}.md"),
    )


@requires_lualatex
def test_valid_math_node_compiles_clean():
    node = _node("math.valid", r"\[ \frac{1}{2} + \frac{1}{2} = 1 \]")
    diags = check_node_tex_compile(node)
    assert diags == []


@requires_lualatex
def test_broken_tex_yields_one_compile_error():
    node = _node("math.broken", r"\[ \frac{1}{ \]")
    diags = check_node_tex_compile(node)
    assert len(diags) == 1
    diag = diags[0]
    assert diag.level == "error"
    assert diag.node_id == "math.broken"
    assert diag.code == "TEX-COMPILE"
    assert diag.file_path == node.file_path
    assert diag.message  # non-empty, carries the parsed TeX error line


@requires_lualatex
def test_declared_macro_is_available_during_compile():
    node = _node("math.macro", r"$\GG$")
    diags = check_node_tex_compile(node, declared_macros={"GG": r"\mathbb{G}"})
    assert diags == []


def test_missing_lualatex_skips_gracefully():
    node = _node("math.skip", r"\[ \frac{1}{ \]")
    # Force the absent-binary path regardless of the host machine.
    diags = check_node_tex_compile(node, lualatex_bin="/nonexistent/lualatex-binary")
    assert diags == []
```

- [ ] Run it; expect **FAIL** (`ModuleNotFoundError: tools.knowledge.tex_compile_check`):

```
uv run --extra dev python -m pytest tests/test_tex_compile_check.py
```

- [ ] Create `tools/knowledge/tex_compile_check.py` with the full implementation:

```python
"""Compile-time gate: project a node to standard LaTeX and compile with lualatex.

This is OPT-IN. Callers run it only behind a ``strict_tex_compile`` flag. When
``lualatex`` is unavailable the gate returns ``[]`` so CI without TeX is
unaffected. A non-zero compile means the node's math is not standard,
compilable LaTeX; the gate emits one rejectable ``TEX-COMPILE`` diagnostic.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.knowledge.models import Node
from tools.knowledge.tex_projector import project_node_to_latex
from tools.knowledge.validator import Diagnostic

_COMPILE_TIMEOUT_SECONDS = 60
_TEX_SOURCE_NAME = "node.tex"


def _first_error_line(stdout: str) -> str:
    """Return the first ``! ``-prefixed TeX error line, or a generic fallback."""
    for line in stdout.splitlines():
        if line.startswith("! "):
            return line[2:].strip()
    return "lualatex compilation failed (no '!' error line found in output)"


def check_node_tex_compile(
    node: Node,
    *,
    declared_macros: dict[str, str] | None = None,
    lualatex_bin: str | None = None,
) -> list[Diagnostic]:
    """Compile the node's projected LaTeX; return diagnostics on failure.

    Returns ``[]`` when ``lualatex`` is absent (graceful skip) or when the
    document compiles cleanly. On failure returns exactly one
    ``Diagnostic(code="TEX-COMPILE")`` carrying the first parsed TeX error line.
    """
    binary = lualatex_bin or shutil.which("lualatex")
    if binary is None or shutil.which(binary) is None:
        return []

    macros = declared_macros or {}
    latex = project_node_to_latex(node, macros=macros)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / _TEX_SOURCE_NAME).write_text(latex, encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    binary,
                    "--interaction=nonstopmode",
                    "--halt-on-error",
                    _TEX_SOURCE_NAME,
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return [
                Diagnostic(
                    "error",
                    node.id,
                    f"lualatex compile timed out after {_COMPILE_TIMEOUT_SECONDS}s",
                    node.file_path,
                    code="TEX-COMPILE",
                )
            ]

        if completed.returncode == 0:
            return []

        message = _first_error_line(completed.stdout)
        return [
            Diagnostic(
                "error",
                node.id,
                f"lualatex compile failed: {message}",
                node.file_path,
                code="TEX-COMPILE",
            )
        ]
```

Note: `shutil.which(binary)` is used twice deliberately — once to resolve `lualatex` from `PATH` when `lualatex_bin` is `None`, and once to confirm an explicitly-passed `lualatex_bin` actually exists/is executable (so the `test_missing_lualatex_skips_gracefully` path with `/nonexistent/lualatex-binary` returns `[]`).

- [ ] Run it; expect **PASS** (the three `requires_lualatex` tests run on this dev machine where `lualatex` is present; the skip test always runs):

```
uv run --extra dev python -m pytest tests/test_tex_compile_check.py
```

- [ ] Commit (new files must be `git add`ed — `-am` alone would miss untracked files):

```
git add tools/knowledge/tex_compile_check.py tests/test_tex_compile_check.py
git commit -m "feat(knowledge): add lualatex compile gate (TEX-COMPILE diagnostics)"
```

---

## Task 3: Wire the gate into `check.py`

**Files:**
- Modify: `tools/knowledge/check.py`
- Test: `tests/test_check.py`

Add a `strict_tex_compile: bool = False` parameter to `check_knowledge_base` (mirroring the existing `strict_lean_git` pattern) and a `--strict-tex-compile` CLI flag in `main()`. When set, run `check_node_tex_compile` per node right after `check_node_math`, passing `config.math.macros` (the full `dict[str, str]`, since the projector needs expansions, not just names).

- [ ] Add a CLI integration test to `tests/test_check.py` inside `class TestCheckCLI`:

```python
    def test_cli_strict_tex_compile_flag_is_accepted(self, tmp_path: Path) -> None:
        # The flag must parse and run cleanly on a valid math node. When
        # lualatex is absent the gate skips, so this asserts only that the flag
        # is wired and does not crash, and that a valid node stays error-free.
        nodes_dir = tmp_path / "nodes" / "math"
        nodes_dir.mkdir(parents=True)
        (nodes_dir / "ok.md").write_text(
            "---\n"
            "id: math.ok\n"
            "title: OK\n"
            "kind: theorem\n"
            "status: admitted\n"
            "uses: []\n"
            "verification:\n"
            "  statement: accepted\n"
            "  proof: accepted\n"
            "---\n\n"
            "# OK\n\n"
            r"\[ x = 1 \]" + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "tools.knowledge.check",
                str(tmp_path), "--strict-tex-compile",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "0 error(s)" in result.stdout
```

- [ ] Run it; expect **FAIL** (the parser rejects the unknown `--strict-tex-compile` argument, so `returncode == 2`):

```
uv run --extra dev python -m pytest "tests/test_check.py::TestCheckCLI::test_cli_strict_tex_compile_flag_is_accepted"
```

- [ ] Edit `tools/knowledge/check.py` — add the import (after the existing `latex_check` import on line 16):

```python
from tools.knowledge.tex_compile_check import check_node_tex_compile
```

- [ ] Edit the `check_knowledge_base` signature to add the new flag:

```python
def check_knowledge_base(
    root: Path,
    *,
    lean_root: Path | None = None,
    config_path: Path | None = None,
    strict_lean_git: bool = False,
    strict_lean_placeholders: bool = False,
    strict_tex_compile: bool = False,
) -> list[Diagnostic]:
```

- [ ] In the `nodes_dir` loop, immediately after the `check_node_math(...)` line, add the gated call:

```python
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            if strict_tex_compile:
                diags.extend(check_node_tex_compile(node, declared_macros=config.math.macros))
```

- [ ] In the `staged_dir` loop, immediately after its `check_node_math(...)` line, add the same gated call:

```python
            diags.extend(check_node_math(node, declared_macros=set(config.math.macros)))
            if strict_tex_compile:
                diags.extend(check_node_tex_compile(node, declared_macros=config.math.macros))
```

- [ ] In `main()`, add the CLI flag (after the existing `--strict-lean-placeholders` argument):

```python
    parser.add_argument(
        "--strict-tex-compile", action="store_true",
        help="compile each node's projected LaTeX with lualatex (skips if lualatex absent)",
    )
```

- [ ] In `main()`, pass the flag through to `check_knowledge_base`:

```python
    diags = check_knowledge_base(
        root,
        lean_root=lean_root,
        config_path=config_path,
        strict_lean_git=args.strict_lean_git,
        strict_lean_placeholders=args.strict_lean_placeholders,
        strict_tex_compile=args.strict_tex_compile,
    )
```

- [ ] Run the new test; expect **PASS**:

```
uv run --extra dev python -m pytest "tests/test_check.py::TestCheckCLI::test_cli_strict_tex_compile_flag_is_accepted"
```

- [ ] Run the full `check` test module to confirm no regression:

```
uv run --extra dev python -m pytest tests/test_check.py
```

- [ ] Commit:

```
git commit -am "feat(knowledge): wire opt-in --strict-tex-compile into check"
```

---

## Task 4: Wire the gate into `admission_pipeline.py`

**Files:**
- Modify: `tools/knowledge/admission_pipeline.py`
- Test: `tests/test_admission_pipeline.py`

Add a `strict_tex_compile: bool = False` parameter to `run_admission_pipeline`. When set, append a `("tex_compile", ...)` entry to the `gate_checks` list (so it runs after the existing `dag` entry; the post-loop `write` gate stays last), loading macros via `load_project_config(knowledge_root)`. The existing `_gate(name, diags)` helper turns the diagnostics into a `PipelineGate`. When the flag is off (default) the gate list is unchanged.

- [ ] Add a gate test to `tests/test_admission_pipeline.py` (top-level function near the existing helpers, plus a `requires_lualatex` marker at module top):

```python
import shutil

import pytest

requires_lualatex = pytest.mark.skipif(
    shutil.which("lualatex") is None,
    reason="lualatex not installed; tex_compile gate skips gracefully",
)


def _write_theorem_with_broken_tex(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: algebra.broken_tex\n"
        "title: Broken TeX\n"
        "kind: theorem\n"
        "status: staged\n"
        "uses: []\n"
        "verification:\n  statement: accepted\n  proof: accepted\n"
        "generality:\n  reviewed: true\n"
        "---\n\n"
        "# Broken TeX\n\n*Proof.* Done.\n\n"
        r"\[ \frac{1}{ \]" + "\n",
        encoding="utf-8",
    )


@requires_lualatex
def test_tex_compile_gate_blocks_broken_tex_when_enabled(tmp_path):
    kb = tmp_path / "knowledge"
    staged = kb / "staged" / "algebra" / "broken.md"
    (kb / "nodes").mkdir(parents=True)
    _write_theorem_with_broken_tex(staged)

    result = run_admission_pipeline(
        staged, kb, require_reviews=False, strict_tex_compile=True
    )

    assert not result.success
    gate = next(g for g in result.gates if g.name == "tex_compile")
    assert gate.status == "failed"
    assert gate.messages  # carries the TEX-COMPILE error message
    assert staged.exists()  # blocked node is not moved


def test_tex_compile_gate_absent_by_default(tmp_path):
    kb = tmp_path / "knowledge"
    staged = kb / "staged" / "algebra" / "broken.md"
    (kb / "nodes").mkdir(parents=True)
    _write_theorem_with_broken_tex(staged)

    result = run_admission_pipeline(staged, kb, require_reviews=False)

    assert "tex_compile" not in [g.name for g in result.gates]
    assert result.success  # broken TeX is irrelevant without the flag
```

- [ ] Run it; expect **FAIL** (`run_admission_pipeline()` got an unexpected keyword argument `strict_tex_compile`):

```
uv run --extra dev python -m pytest tests/test_admission_pipeline.py -k tex_compile
```

- [ ] Edit `tools/knowledge/admission_pipeline.py` — add imports (alongside the existing `parser`/`validator` imports near the top):

```python
from tools.knowledge.config import load_project_config
from tools.knowledge.tex_compile_check import check_node_tex_compile
```

- [ ] Edit the `run_admission_pipeline` signature to add the new flag:

```python
def run_admission_pipeline(
    staged_path: Path,
    knowledge_root: Path,
    *,
    require_reviews: bool = True,
    dry_run: bool = False,
    strict_tex_compile: bool = False,
) -> PipelineResult:
```

- [ ] After the existing `gate_checks = [...]` list literal (and before the `for name, diags in gate_checks:` loop), append the opt-in gate so it runs after `dag`:

```python
    if strict_tex_compile:
        config = load_project_config(knowledge_root)
        gate_checks.append(
            ("tex_compile", check_node_tex_compile(node, declared_macros=config.math.macros))
        )
```

- [ ] Add the `--strict-tex-compile` CLI flag in `main()` (after the existing `--dry-run` argument):

```python
    parser.add_argument(
        "--strict-tex-compile", action="store_true",
        help="compile the staged node's projected LaTeX with lualatex (skips if absent)",
    )
```

- [ ] Pass it through in `main()`'s `run_admission_pipeline(...)` call:

```python
    result = run_admission_pipeline(
        args.staged_path,
        args.knowledge_root,
        require_reviews=not args.no_reviews,
        dry_run=args.dry_run,
        strict_tex_compile=args.strict_tex_compile,
    )
```

- [ ] Run the gate tests; expect **PASS**:

```
uv run --extra dev python -m pytest tests/test_admission_pipeline.py -k tex_compile
```

- [ ] Run the full admission module to confirm gate-order tests still pass (the default-order test asserts `[schema, generality, verification, reviews, dag, write]`, which the opt-in gate does not disturb):

```
uv run --extra dev python -m pytest tests/test_admission_pipeline.py
```

- [ ] Commit:

```
git commit -am "feat(knowledge): add opt-in tex_compile admission gate"
```

---

## Task 5: Full-suite verification

**Files:** none (verification only)

- [ ] Run the full test suite to confirm no regression across the project:

```
uv run --extra dev python -m pytest
```

- [ ] Expect **PASS** (the `requires_lualatex`-marked tests run on this dev machine; on a TeX-less host they `skip`, and the gate-skip and default-off tests still pass).

---

## Done criteria

- [ ] `tools/knowledge/tex_projector.py` exists and `project_node_to_latex(node, *, macros)` returns a standard `article` document whose preamble includes `\documentclass{article}`, `\usepackage{amsmath,amssymb,amsthm}`, `\usepackage{tikz}` + `\usetikzlibrary{cd}`, and one zero-arg `\newcommand` per macro; display spans → `\[ ... \]`, inline spans → `$ ... $`; prose is discarded.
- [ ] `tools/knowledge/tex_compile_check.py` exists and `check_node_tex_compile(node, *, declared_macros=None, lualatex_bin=None)` returns `[]` when `lualatex` is absent or the doc compiles, and exactly one `Diagnostic(level="error", code="TEX-COMPILE", node_id=node.id, file_path=node.file_path)` (message = first `! ` line) on failure, using `--interaction=nonstopmode --halt-on-error`, a `TemporaryDirectory`, and a 60s timeout.
- [ ] `check.py` exposes `strict_tex_compile` (default `False`) and the `--strict-tex-compile` CLI flag; the gate runs per node right after `check_node_math`, passing `config.math.macros`.
- [ ] `admission_pipeline.py` exposes `strict_tex_compile` (default `False`) and the `--strict-tex-compile` CLI flag; the opt-in `("tex_compile", ...)` gate runs after `dag`, loads macros via `load_project_config`, and is absent from the gate list when the flag is off.
- [ ] All new tests pass; `requires_lualatex` tests skip cleanly on a TeX-less host; the suite is green via `uv run --extra dev python -m pytest`.
- [ ] The gate is OFF by default everywhere; nothing new runs in CI (which has no TeX) unless a flag is explicitly passed.

## Next plans

- **Content-hash caching of compile results** — at KB scale, recompiling every node on each run is wasteful. A later plan should key compile results by a hash of `(projected_latex, lualatex_version)` and short-circuit on a cache hit. (Out of scope here.)
- **TikZ → SVG / PDF rendering pipeline** (`dvisvgm`) — turning tikz-cd diagrams into rendered figures for the static site is a separate concern from this *gate*; the preamble already loads `tikz`/`cd` so the projection compiles, but rendering output is deferred. (Out of scope here.)
- **Macro-arity inference** — declared macros are currently emitted as zero-argument `\newcommand`s; supporting `\newcommand{\name}[n]{...}` requires inferring or declaring arity. (Out of scope here.)
- **Making the gate default-on / installing TeX in CI** — once the gate is proven on staged-node output, a future plan can add TeX to CI and flip the default. (Out of scope here.)
