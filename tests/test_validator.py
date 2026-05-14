from pathlib import Path

import pytest

from tools.knowledge.parser import parse_file, parse_node
from tools.knowledge.validator import validate_node

NODES_DIR = Path("docs/knowledge/nodes/strategic_games")
STAGED_DIR = Path("docs/knowledge/staged")
INVALID_DIR = Path("tests/fixtures/invalid")


class TestValidAdmitted:
    def test_strategic_game_valid(self):
        node = parse_file(NODES_DIR / "strategic_game.md")
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_all_admitted_nodes_valid(self):
        for p in sorted(NODES_DIR.rglob("*.md")):
            node = parse_file(p)
            diags = validate_node(node, is_staged_dir=False)
            errors = [d for d in diags if d.level == "error"]
            assert errors == [], f"{p.name}: {errors}"


class TestValidStaged:
    def test_staged_mixed_strategy(self):
        node = parse_file(STAGED_DIR / "mixed_strategy.md")
        diags = validate_node(node, is_staged_dir=True)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []


class TestMissingFields:
    def test_missing_kind_and_status(self):
        node = parse_file(INVALID_DIR / "missing_fields.md")
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        msgs = [d.message for d in errors]
        assert any("kind" in m for m in msgs)
        assert any("status" in m for m in msgs)


class TestDirectoryStatusConsistency:
    def test_admitted_in_staged_dir(self):
        node = parse_file(INVALID_DIR / "wrong_status_in_staged.md")
        diags = validate_node(node, is_staged_dir=True)
        errors = [d for d in diags if d.level == "error"]
        assert any("admitted status" in d.message for d in errors)

    def test_staged_in_nodes_dir(self):
        node = parse_file(STAGED_DIR / "mixed_strategy.md")
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert any("staged status" in d.message for d in errors)


class TestVerificationFields:
    def test_reject_both_statement_and_definition(self):
        text = """---
id: test.both
title: Both Fields
kind: definition
status: admitted
uses: []
verification:
  statement: accepted
  definition: accepted
---

# Both

Test.
"""
        node = parse_node(text)
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        assert any("both" in d.message.lower() for d in errors)


class TestForbiddenHeadings:
    def test_forbidden_operational_heading(self):
        node = parse_file(INVALID_DIR / "forbidden_heading.md")
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        msgs = " ".join(d.message for d in errors)
        assert "Implementation Notes" in msgs or "implementation notes" in msgs.lower()
        assert "Status" in msgs or "status" in msgs.lower()


class TestSourceSpanBinding:
    def test_bad_artifact_reference(self):
        node = parse_file(INVALID_DIR / "bad_span_ref.md")
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        assert any("nonexistent-artifact" in d.message for d in errors)
