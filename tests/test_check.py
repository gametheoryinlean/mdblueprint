"""Tests for the check CLI and check_knowledge_base function."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.knowledge.check import check_knowledge_base

_TESTS_DIR = Path(__file__).parent
KNOWLEDGE_ROOT = _TESTS_DIR.parent / "docs" / "knowledge"
LEAN_FIXTURES = _TESTS_DIR / "fixtures" / "lean"


class TestCheckKnowledgeBase:
    def test_valid_knowledge_base_no_errors(self) -> None:
        diags = check_knowledge_base(KNOWLEDGE_ROOT)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_nonexistent_root_returns_empty(self) -> None:
        diags = check_knowledge_base(Path("/nonexistent/path"))
        assert diags == []

    def test_with_lean_root(self) -> None:
        diags = check_knowledge_base(KNOWLEDGE_ROOT, lean_root=LEAN_FIXTURES)
        for d in diags:
            assert d.level in ("error", "warning")

    def test_with_nonexistent_lean_root(self) -> None:
        diags = check_knowledge_base(
            KNOWLEDGE_ROOT, lean_root=Path("/nonexistent/lean")
        )
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_detects_invalid_nodes(self, tmp_path: Path) -> None:
        nodes_dir = tmp_path / "nodes" / "test"
        nodes_dir.mkdir(parents=True)
        bad_node = nodes_dir / "bad.md"
        bad_node.write_text("---\nid: bad\n---\nno kind or status\n")
        diags = check_knowledge_base(tmp_path)
        errors = [d for d in diags if d.level == "error"]
        assert len(errors) > 0

    def test_topic_registry_checks_primary_and_membership_topics(self, tmp_path: Path) -> None:
        nodes_dir = tmp_path / "nodes" / "legacy"
        nodes_dir.mkdir(parents=True)
        (tmp_path / "mdblueprint.yml").write_text(
            "site:\n"
            "  title: Topic Registry Fixture\n"
            "topics:\n"
            "  - id: algebra.groups\n"
            "    title: Groups\n"
            "    aliases: [groups]\n"
            "  - id: algebra.monoids\n"
            "    title: Monoids\n",
            encoding="utf-8",
        )
        (nodes_dir / "bad.md").write_text(
            "---\n"
            "id: legacy.group\n"
            "title: Group\n"
            "kind: definition\n"
            "status: admitted\n"
            "primary_topic: groups\n"
            "topics:\n"
            "  - groups\n"
            "  - algebra.rings\n"
            "uses: []\n"
            "---\n\n"
            "# Group\n",
            encoding="utf-8",
        )

        diags = check_knowledge_base(tmp_path)
        errors = [d.message for d in diags if d.level == "error"]
        warnings = [d.message for d in diags if d.level == "warning"]

        assert any("primary_topic 'groups' is an alias" in msg for msg in errors)
        assert any("topics entry 'groups' is an alias" in msg for msg in errors)
        assert any("topics entry 'algebra.rings' is not in the canonical topic registry" in msg for msg in warnings)


class TestCheckCLI:
    def test_cli_exit_zero_on_valid(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "tools.knowledge.check", str(KNOWLEDGE_ROOT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "0 error(s)" in result.stdout

    def test_cli_exit_one_on_errors(self, tmp_path: Path) -> None:
        nodes_dir = tmp_path / "nodes" / "test"
        nodes_dir.mkdir(parents=True)
        bad = nodes_dir / "bad.md"
        bad.write_text("---\nid: bad\n---\n")
        result = subprocess.run(
            [sys.executable, "-m", "tools.knowledge.check", str(tmp_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_cli_with_lean_root(self) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "tools.knowledge.check",
                str(KNOWLEDGE_ROOT),
                "--lean-root", str(LEAN_FIXTURES),
            ],
            capture_output=True, text=True,
        )
        assert "error(s)" in result.stdout
