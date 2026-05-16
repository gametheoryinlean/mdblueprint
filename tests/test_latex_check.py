import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.check import check_knowledge_base
from tools.knowledge.parser import parse_file


def _write_node(path: Path, *, node_id: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = textwrap.dedent(body).strip()
    path.write_text(
        (
            "---\n"
            f"id: {node_id}\n"
            "title: Math Node\n"
            "kind: theorem\n"
            "status: admitted\n"
            "uses: []\n"
            "verification:\n"
            "  statement: accepted\n"
            "  proof: accepted\n"
            "---\n\n"
            "# Math Node\n\n"
            f"{normalized_body}\n"
        ),
        encoding="utf-8",
    )


def test_static_math_check_reports_unmatched_inline_delimiter(tmp_path):
    node_path = tmp_path / "bad.md"
    _write_node(node_path, node_id="math.bad_inline", body="This has $x_i without a close delimiter.")

    from tools.knowledge.latex_check import check_node_math

    diags = check_node_math(parse_file(node_path))

    assert any(d.level == "error" for d in diags)
    assert any("math.bad_inline" == d.node_id for d in diags)
    assert any(str(node_path) == str(d.file_path) for d in diags)
    assert any("line" in d.message and "unmatched" in d.message.lower() for d in diags)


def test_static_math_check_reports_mismatched_environment(tmp_path):
    node_path = tmp_path / "bad_env.md"
    _write_node(
        node_path,
        node_id="math.bad_env",
        body=r"""
        \[
        \begin{aligned}
        x &= y
        \end{cases}
        \]
        """,
    )

    from tools.knowledge.latex_check import check_node_math

    diags = check_node_math(parse_file(node_path))

    assert any("begin{aligned}" in d.message and "end{cases}" in d.message for d in diags)


def test_check_knowledge_base_runs_static_math_diagnostics(tmp_path):
    node_path = tmp_path / "nodes" / "math" / "bad.md"
    _write_node(node_path, node_id="math.bad", body=r"Broken display math: \[ x_i^2.")

    diags = check_knowledge_base(tmp_path)

    assert any(d.level == "error" and d.node_id == "math.bad" for d in diags)
    assert any(d.file_path == node_path for d in diags)


def test_check_cli_prints_node_and_file_for_static_math_errors(tmp_path):
    node_path = tmp_path / "nodes" / "math" / "bad.md"
    _write_node(node_path, node_id="math.cli_bad", body="Broken $x_i")

    result = subprocess.run(
        [sys.executable, "-m", "tools.knowledge.check", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "math.cli_bad" in result.stdout
    assert str(node_path) in result.stdout
    assert "unmatched" in result.stdout.lower()


def test_valid_inline_display_and_environment_math_passes(tmp_path):
    node_path = tmp_path / "nodes" / "math" / "valid.md"
    _write_node(
        node_path,
        node_id="math.valid",
        body=r"""
        Inline math $x_i^2$ and \(y_i^2\) should pass.

        \[
        \begin{aligned}
        x_i^2 &= y_i^2 \\
        z_i &= x_i + y_i
        \end{aligned}
        \]

        $$
        a_i = b_i
        $$
        """,
    )

    errors = [d for d in check_knowledge_base(tmp_path) if d.level == "error"]

    assert errors == []


def test_static_math_check_accepts_katex_builtin_macros(tmp_path):
    node_path = tmp_path / "nodes" / "math" / "katex_builtins.md"
    _write_node(
        node_path,
        node_id="math.katex_builtins",
        body=r"""
        Built-in KaTeX macros should not require project macro overrides:
        $x \notin C$, $C_1,\ldots,C_n$, $x^\ast$, and
        $\bigcap_i C_i \ne \emptyset$.

        We also use $\widetilde G$, $\langle x,y\rangle$,
        $A\setminus B$, $\limsup_n a_n$, $P \Rightarrow Q$,
        and $P \Longleftrightarrow Q$.
        """,
    )

    errors = [d for d in check_knowledge_base(tmp_path) if d.level == "error"]

    assert errors == []


def test_static_math_check_uses_project_macro_config(tmp_path):
    node_path = tmp_path / "nodes" / "math" / "macro.md"
    _write_node(node_path, node_id="math.macro", body=r"Configured macro $\R$ should pass.")

    errors_without_config = [d for d in check_knowledge_base(tmp_path) if d.level == "error"]

    (tmp_path / "mdblueprint.yml").write_text(
        textwrap.dedent(
            r"""
            site:
              title: Macro Blueprint
            math:
              macros:
                R: "\\mathbb{R}"
            """
        ).strip(),
        encoding="utf-8",
    )
    errors_with_config = [d for d in check_knowledge_base(tmp_path) if d.level == "error"]

    assert any("unknown macro" in d.message and r"\R" in d.message for d in errors_without_config)
    assert errors_with_config == []
