from pathlib import Path

import pytest

from tools.knowledge.parser import parse_file, parse_node
from tools.knowledge.validator import validate_node

_TESTS_DIR = Path(__file__).parent
NODES_DIR = _TESTS_DIR.parent / "docs" / "knowledge" / "nodes" / "strategic_games"
STAGED_DIR = _TESTS_DIR.parent / "docs" / "knowledge" / "staged"
INVALID_DIR = _TESTS_DIR / "fixtures" / "invalid"


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


class TestInvalidKindAndStatus:
    def test_topic_kind_is_valid(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: topic\nstatus: admitted\nuses: []\n---\n\n# X\n")
        diags = validate_node(node)
        assert not any("invalid kind" in d.message for d in diags)

    def test_concept_kind_remains_valid(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: concept\nstatus: admitted\nuses: []\n---\n\n# X\n")
        diags = validate_node(node)
        assert not any("invalid kind" in d.message for d in diags)

    def test_invalid_kind(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: bogus\nstatus: admitted\nuses: []\n---\n\n# X\n")
        diags = validate_node(node)
        assert any("invalid kind" in d.message for d in diags)

    def test_invalid_status(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: definition\nstatus: bogus\nuses: []\n---\n\n# X\n")
        diags = validate_node(node)
        assert any("invalid status" in d.message for d in diags)

    def test_missing_title(self):
        node = parse_node("---\nid: t.x\nkind: definition\nstatus: admitted\nuses: []\n---\n\n# X\n")
        diags = validate_node(node)
        assert any("title" in d.message for d in diags)


class TestVerificationValues:
    def test_invalid_statement_value(self):
        text = "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\nverification:\n  statement: bogus\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        assert any("verification.statement" in d.message for d in diags)

    def test_invalid_definition_value(self):
        text = "---\nid: t.x\ntitle: X\nkind: definition\nstatus: admitted\nuses: []\nverification:\n  definition: bogus\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        assert any("verification.definition" in d.message for d in diags)

    def test_invalid_proof_value(self):
        text = "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\nverification:\n  statement: accepted\n  proof: bogus\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        assert any("verification.proof" in d.message for d in diags)

    def test_invalid_alignment_value(self):
        text = "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\nverification:\n  statement: accepted\n  alignment: bogus\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        assert any("verification.alignment" in d.message for d in diags)

    def test_statement_on_definition_kind_warns(self):
        text = "---\nid: t.x\ntitle: X\nkind: definition\nstatus: admitted\nuses: []\nverification:\n  statement: accepted\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        warns = [d for d in diags if d.level == "warning"]
        assert any("definition" in d.message and "statement" in d.message for d in warns)

    def test_definition_on_theorem_kind_warns(self):
        text = "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\nverification:\n  definition: accepted\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        warns = [d for d in diags if d.level == "warning"]
        assert any("statement" in d.message and "definition" in d.message for d in warns)


class TestExternalTheorem:
    def test_external_theorem_missing_lean(self):
        text = "---\nid: t.x\ntitle: X\nkind: external-theorem\nstatus: admitted\nuses: []\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node)
        assert any("external-theorem" in d.message and "lean" in d.message for d in diags)


class TestLeanStatusPolicy:
    def test_admitted_theorem_without_lean_is_valid(self):
        text = (
            "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\n"
            "verification:\n  statement: accepted\n  proof: accepted\n"
            "---\n\n# X\n\n*Proof.* Done.\n"
        )
        node = parse_node(text)
        errors = [d for d in validate_node(node) if d.level == "error"]
        assert errors == []

    def test_formalized_without_lean_is_error(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: theorem\nstatus: formalized\nuses: []\n---\n\n# X\n")
        assert any("formalized" in d.message and "lean" in d.message for d in validate_node(node))

    def test_proved_without_lean_is_error(self):
        node = parse_node("---\nid: t.x\ntitle: X\nkind: theorem\nstatus: proved\nuses: []\n---\n\n# X\n")
        assert any("proved" in d.message and "lean" in d.message for d in validate_node(node))

    def test_alignment_without_lean_is_error(self):
        node = parse_node(
            "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: admitted\nuses: []\n"
            "verification:\n  statement: accepted\n  proof: accepted\n  alignment: aligned\n"
            "---\n\n# X\n\n*Proof.* Done.\n"
        )
        assert any("alignment" in d.message and "lean" in d.message for d in validate_node(node))

    def test_staged_alignment_without_lean_is_warning_not_error(self):
        node = parse_node(
            "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: staged\nuses: []\n"
            "verification:\n  statement: accepted\n  alignment: aligned\n"
            "---\n\n# X\n"
        )
        diags = validate_node(node, is_staged_dir=True)
        assert not any(d.level == "error" for d in diags)
        assert any(d.level == "warning" and "alignment" in d.message for d in diags)


class TestDiagnosticStr:
    def test_with_file_path(self):
        from tools.knowledge.validator import Diagnostic
        d = Diagnostic("error", "test.node", "test msg", Path("foo.md"))
        assert "[ERROR] foo.md (test.node): test msg" == str(d)

    def test_without_file_path(self):
        from tools.knowledge.validator import Diagnostic
        d = Diagnostic("warning", "test.node", "test msg")
        assert "[WARNING] test.node: test msg" == str(d)


class TestTopicMembership:
    def _node(self, **kwargs):
        from tools.knowledge.models import Node
        return Node(id="t.x", title="X", kind="definition", status="admitted", **kwargs)

    def test_primary_topic_not_in_topics_is_error(self):
        node = self._node(primary_topic="algebra", topics=["linear_programming"])
        diags = validate_node(node)
        assert any("primary_topic" in d.message and d.level == "error" for d in diags)

    def test_primary_topic_in_topics_is_valid(self):
        node = self._node(primary_topic="algebra", topics=["algebra", "linear_programming"])
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_topics_without_primary_topic_is_valid(self):
        node = self._node(topics=["algebra", "linear_programming"])
        diags = validate_node(node)
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_empty_string_in_topics_is_error(self):
        node = self._node(topics=["algebra", ""])
        diags = validate_node(node)
        assert any("topics entries" in d.message and d.level == "error" for d in diags)


class TestRequireSourceSpans:
    def test_definition_missing_spans_warns_when_required(self):
        text = "---\nid: t.x\ntitle: X\nkind: definition\nstatus: staged\nuses: []\n---\n\n# X\n\nA definition.\n"
        node = parse_node(text)
        diags = validate_node(node, require_source_spans=True)
        warns = [d for d in diags if d.level == "warning" and "source.spans" in d.message]
        assert warns, "expected a source.spans warning for definition with no source"

    def test_theorem_missing_spans_warns_when_required(self):
        text = "---\nid: t.x\ntitle: X\nkind: theorem\nstatus: staged\nuses: []\n---\n\n# X\n\nStatement.\n"
        node = parse_node(text)
        diags = validate_node(node, require_source_spans=True)
        warns = [d for d in diags if d.level == "warning" and "source.spans" in d.message]
        assert warns, "expected a source.spans warning for theorem with no source"

    def test_missing_spans_no_warning_without_flag(self):
        text = "---\nid: t.x\ntitle: X\nkind: definition\nstatus: staged\nuses: []\n---\n\n# X\n\nA definition.\n"
        node = parse_node(text)
        diags = validate_node(node, require_source_spans=False)
        warns = [d for d in diags if d.level == "warning" and "source.spans" in d.message]
        assert warns == []

    def test_math_node_with_spans_no_warning(self):
        text = (
            "---\nid: t.x\ntitle: X\nkind: definition\nstatus: staged\nuses: []\n"
            "source:\n  artifacts:\n    - id: a1\n      path: foo.pdf\n"
            "  spans:\n    - artifact: a1\n      locator: \"p.42\"\n"
            "---\n\n# X\n"
        )
        node = parse_node(text)
        diags = validate_node(node, require_source_spans=True)
        warns = [d for d in diags if d.level == "warning" and "source.spans" in d.message]
        assert warns == []

    def test_non_math_node_missing_spans_no_warning(self):
        text = "---\nid: t.x\ntitle: X\nkind: task\nstatus: staged\nuses: []\n---\n\n# X\n"
        node = parse_node(text)
        diags = validate_node(node, require_source_spans=True)
        warns = [d for d in diags if d.level == "warning" and "source.spans" in d.message]
        assert warns == []


class TestSourceSpanFormat:
    def test_unknown_locator_format_warns(self):
        text = (
            "---\nid: t.x\ntitle: X\nkind: definition\nstatus: admitted\nuses: []\n"
            "source:\n  artifacts:\n    - id: a1\n      path: foo.pdf\n"
            "  spans:\n    - artifact: a1\n      locator: p42\n      format: unknown-fmt\n"
            "---\n\n# X\n"
        )
        node = parse_node(text)
        diags = validate_node(node)
        warns = [d for d in diags if d.level == "warning"]
        assert any("unknown-fmt" in d.message for d in warns)
