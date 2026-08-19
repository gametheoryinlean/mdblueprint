import textwrap
from pathlib import Path

from tools.knowledge.markdown_check import check_node_markdown
from tools.knowledge.parser import parse_file


def _write_node(path: Path, *, node_id: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_body = textwrap.dedent(body).strip()
    path.write_text(
        (
            "---\n"
            f"id: {node_id}\n"
            "title: Markdown Node\n"
            "kind: theorem\n"
            "status: admitted\n"
            "uses: []\n"
            "verification:\n"
            "  statement: accepted\n"
            "  proof: accepted\n"
            "---\n\n"
            "# Markdown Node\n\n"
            f"{normalized_body}\n"
        ),
        encoding="utf-8",
    )


def _diags(tmp_path, body):
    node_path = tmp_path / "node.md"
    _write_node(node_path, node_id="md.node", body=body)
    return check_node_markdown(parse_file(node_path))


def test_warns_when_list_has_no_blank_line_before_it(tmp_path):
    diags = _diags(tmp_path, """
        Elliptic elements play a key role in:
        - The elliptic representation theory.
        - The elliptic pairing on class functions.
    """)

    assert len(diags) == 1
    assert diags[0].level == "warning"
    assert diags[0].code == "md-list-needs-blank-line"


def test_warns_for_ordered_list_without_blank_line(tmp_path):
    diags = _diags(tmp_path, """
        The construction proceeds in two steps:
        1. Choose a maximal torus.
        2. Take its centralizer.
    """)

    assert [d.code for d in diags] == ["md-list-needs-blank-line"]


def test_no_warning_when_blank_line_present(tmp_path):
    diags = _diags(tmp_path, """
        Elliptic elements play a key role in:

        - The elliptic representation theory.
        - The elliptic pairing on class functions.
    """)

    assert diags == []


def test_no_warning_for_list_after_heading(tmp_path):
    diags = _diags(tmp_path, """
        ## Properties

        - First property.
        - Second property.
    """)

    assert diags == []


def test_no_warning_for_numbered_prose_line(tmp_path):
    diags = _diags(tmp_path, """
        The theorem was first proved in
        1965. It was later refined.
    """)

    assert diags == []


def test_no_warning_inside_fenced_code_block(tmp_path):
    diags = _diags(tmp_path, """
        Example input:

        ```
        header line
        - not a real list
        ```
    """)

    assert diags == []


def test_warning_reports_the_offending_line_number(tmp_path):
    diags = _diags(tmp_path, """
        Intro paragraph.

        Second intro line:
        - item one
    """)

    # Line numbers are body-relative (body line 1 is the `# ` heading),
    # matching the convention used by check_node_math.
    assert len(diags) == 1
    assert "line 6" in diags[0].message
