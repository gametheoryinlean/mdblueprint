"""Tests for `tools.knowledge.lean_reverse_check`."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.lean_index import index_lean_project
from tools.knowledge.lean_reverse_check import (
    ReverseDiagnostic,
    check_reverse_links,
    main,
    summarise,
)


def _write_knowledge(tmp_path: Path, lean_root: Path, *, node_body: str = "") -> Path:
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
    (node_dir / "one.md").write_text(node_body, encoding="utf-8")
    return knowledge_root


def _write_lean(lean_root: Path, *, contents: str) -> None:
    lean_file = lean_root / "Example" / "Basic.lean"
    lean_file.parent.mkdir(parents=True, exist_ok=True)
    lean_file.write_text(contents, encoding="utf-8")


def _load(knowledge_root: Path) -> tuple[list, dict]:
    ctx = KnowledgeContext.load(knowledge_root)
    indexes = {
        repo_id: index_lean_project(repo.local_path, repository=repo)
        for repo_id, repo in ctx.config.lean.repositories.items()
    }
    return list(ctx.nodes_by_id.values()), indexes


def test_ok_when_forward_and_reverse_agree(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents=textwrap.dedent(
            """
            /-- Documented thing.

            Blueprint: example.one
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            lean:
              repository: main
              declarations:
                - Example.thing
            ---

            # One
            """
        ).strip() + "\n",
    )
    nodes, indexes = _load(knowledge_root)
    diags = check_reverse_links(nodes, indexes)
    counts = summarise(diags)
    assert counts["ok"] == 1
    assert counts["md_only"] == 0
    assert counts["lean_only"] == 0
    assert counts["cross_mismatch"] == 0


def test_md_only_when_lean_has_no_marker(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents="def Example.thing : True := True.intro\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            lean:
              repository: main
              declarations:
                - Example.thing
            ---

            # One
            """
        ).strip() + "\n",
    )
    nodes, indexes = _load(knowledge_root)
    diags = check_reverse_links(nodes, indexes)
    cats = [d.category for d in diags]
    assert "md_only" in cats
    assert "cross_mismatch" not in cats


def test_lean_only_when_md_lacks_declaration(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents=textwrap.dedent(
            """
            /-- Implements `example.one`.

            Blueprint: example.one
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
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
    )
    nodes, indexes = _load(knowledge_root)
    diags = check_reverse_links(nodes, indexes)
    cats = [d.category for d in diags]
    assert "lean_only" in cats
    assert "cross_mismatch" not in cats


def test_cross_mismatch_when_directions_disagree(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents=textwrap.dedent(
            """
            /-- Implements `example.real`, but...

            Blueprint: example.real
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            lean:
              repository: main
              declarations:
                - Example.thing
            ---

            # One
            """
        ).strip() + "\n",
    )
    # Add the "real" node so it can be claimed by Lean.
    other = knowledge_root / "nodes" / "example" / "real.md"
    other.write_text(
        textwrap.dedent(
            """
            ---
            id: example.real
            title: Real
            kind: definition
            status: admitted
            ---

            # Real (no lean.declarations entry)
            """
        ).strip() + "\n",
        encoding="utf-8",
    )
    nodes, indexes = _load(knowledge_root)
    diags = check_reverse_links(nodes, indexes)
    cats = [d.category for d in diags]
    # MD points example.one → Example.thing; Lean Blueprint says
    # example.real ← Example.thing. Same decl, both maps non-empty,
    # disjoint node sets → cross_mismatch.
    assert "cross_mismatch" in cats


def test_main_exit_code_zero_when_clean(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
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
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            lean:
              repository: main
              declarations:
                - Example.thing
            ---

            # One
            """
        ).strip() + "\n",
    )
    assert main([str(knowledge_root)]) == 0


def test_main_exit_code_two_when_cross_mismatch(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents=textwrap.dedent(
            """
            /-- Implements `example.real`.

            Blueprint: example.real
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            lean:
              repository: main
              declarations:
                - Example.thing
            ---

            # One
            """
        ).strip() + "\n",
    )
    (knowledge_root / "nodes" / "example" / "real.md").write_text(
        textwrap.dedent(
            """
            ---
            id: example.real
            title: Real
            kind: definition
            status: admitted
            ---

            # Real
            """
        ).strip() + "\n",
        encoding="utf-8",
    )
    assert main([str(knowledge_root)]) == 2


def test_main_strict_flag_promotes_lean_only_to_failure(tmp_path):
    lean_root = tmp_path / "lean"
    _write_lean(
        lean_root,
        contents=textwrap.dedent(
            """
            /-- Implements `example.one`.

            Blueprint: example.one
            -/
            def Example.thing : True := True.intro
            """
        ).strip() + "\n",
    )
    knowledge_root = _write_knowledge(
        tmp_path,
        lean_root,
        node_body=textwrap.dedent(
            """
            ---
            id: example.one
            title: One
            kind: definition
            status: admitted
            ---

            # One (no MD-side lean ref)
            """
        ).strip() + "\n",
    )
    # Without --strict: lean_only is just a warning, exit 0.
    assert main([str(knowledge_root)]) == 0
    # With --strict: lean_only fails the run.
    assert main([str(knowledge_root), "--strict"]) == 1
