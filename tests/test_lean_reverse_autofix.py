"""Tests for `tools.knowledge.lean_reverse_autofix`."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.knowledge.lean_reverse_autofix import main


def _write_knowledge(
    tmp_path: Path,
    lean_root: Path,
    *,
    nodes: dict[str, str],
) -> Path:
    """Write an mdblueprint workspace with the given nodes.

    `nodes` is a {node_id: body} dict; body is the full markdown
    including YAML frontmatter.
    """
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)
    (knowledge_root / "mdblueprint.yml").write_text(
        textwrap.dedent(
            f"""
            site:
              title: Test Blueprint
            lean:
              default_repository: main
              repositories:
                - id: main
                  title: Example Lean Library
                  local_path: {lean_root}
                  web_url: https://example.test/org/repo
                  source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
                  revision: rev1
            """
        ).strip(),
        encoding="utf-8",
    )
    node_dir = knowledge_root / "nodes" / "example"
    node_dir.mkdir(parents=True, exist_ok=True)
    for node_id, body in nodes.items():
        # Filename derived from the last path segment of the node id.
        filename = node_id.rsplit(".", 1)[-1] + ".md"
        (node_dir / filename).write_text(body, encoding="utf-8")
    return knowledge_root


def _write_lean(lean_root: Path, *, file_path: str, contents: str) -> None:
    target = lean_root / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents, encoding="utf-8")


def test_autofix_appends_lean_only_declarations(tmp_path, capsys):
    """A Lean decl marked `Blueprint: example.one` whose node doesn't
    list it should be added to that node's `lean.declarations`."""
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        file_path="Example/Basic.lean",
        contents=textwrap.dedent(
            """
            /-- Documented.

            Blueprint: example.one
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        nodes={
            "example.one": textwrap.dedent(
                """
                ---
                id: example.one
                title: One
                kind: definition
                status: admitted
                ---

                # One
                """
            ).strip() + "\n",
        },
    )
    # Dry run — no file change, exit 0
    rc = main([str(knowledge_root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Example.thing" in out
    assert "Dry run" in out
    # Confirm file unchanged
    text = (knowledge_root / "nodes" / "example" / "one.md").read_text(encoding="utf-8")
    assert "declarations:" not in text

    # Now apply
    rc = main([str(knowledge_root), "--apply"])
    assert rc == 0
    text = (knowledge_root / "nodes" / "example" / "one.md").read_text(encoding="utf-8")
    assert "Example.thing" in text
    assert "lean:" in text
    assert "declarations:" in text


def test_autofix_extends_existing_declarations_list(tmp_path):
    """A node that already has some declarations gets only the missing
    ones appended."""
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        file_path="Example/Basic.lean",
        contents=textwrap.dedent(
            """
            /-- One.

            Blueprint: example.one
            -/
            def Example.first : True := True.intro

            /-- Two.

            Blueprint: example.one
            -/
            def Example.second : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        nodes={
            "example.one": textwrap.dedent(
                """
                ---
                id: example.one
                title: One
                kind: definition
                status: admitted
                lean:
                  repository: main
                  declarations:
                    - Example.first
                ---

                # One
                """
            ).strip() + "\n",
        },
    )
    rc = main([str(knowledge_root), "--apply"])
    assert rc == 0
    text = (knowledge_root / "nodes" / "example" / "one.md").read_text(encoding="utf-8")
    assert "Example.first" in text
    assert "Example.second" in text


def test_autofix_skips_nodes_without_md_target(tmp_path, capsys):
    """A Blueprint marker pointing at a node that doesn't exist in MD
    is *not* auto-promoted; the MD side hasn't created that node."""
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        file_path="Example/Basic.lean",
        contents=textwrap.dedent(
            """
            /-- Floats free.

            Blueprint: example.does_not_exist_in_md
            -/
            def Example.orphan : True := True.intro
            """
        ).strip() + "\n",
    )
    # Knowledge has *no* matching node; only an unrelated one.
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        nodes={
            "example.other": textwrap.dedent(
                """
                ---
                id: example.other
                title: Other
                kind: definition
                status: admitted
                ---

                # Other
                """
            ).strip() + "\n",
        },
    )
    rc = main([str(knowledge_root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No patches to apply" in out or "Example.orphan" not in out


def test_autofix_no_patches_when_clean(tmp_path, capsys):
    """No lean_only warnings -> exit 0 with a happy message."""
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        file_path="Example/Basic.lean",
        contents="def Example.thing : True := True.intro\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        nodes={
            "example.one": textwrap.dedent(
                """
                ---
                id: example.one
                title: One
                kind: definition
                status: admitted
                ---

                # One
                """
            ).strip() + "\n",
        },
    )
    rc = main([str(knowledge_root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No patches" in out
