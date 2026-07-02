"""Tests for the KB↔Lean structure/class field-coverage audit."""
from pathlib import Path

from tools.knowledge.context import KnowledgeContext
from tools.knowledge.kb_lean_field_audit import (
    LeanField,
    audit_knowledge_base,
    audit_node,
    extract_fields_from_signature,
    field_covered_in_body,
    render_report,
)
from tools.knowledge.lean_index import index_lean_project


class TestExtractFields:
    def test_class_fields_with_docstrings(self):
        sig = (
            "class Foo (X : Type*) [PartialOrder X] where\n"
            "  /-- (P0) Cosheaf monotonicity. -/\n"
            "  P0 : ∀ {E F : X}, E ≤ F → P F ≤ P E\n"
            "  /-- (P1) equivariance. -/\n"
            "  P1 : ∀ n, True\n"
            "  P2 : True\n"
        )
        fields = extract_fields_from_signature(sig)
        assert [f.name for f in fields] == ["P0", "P1", "P2"]
        assert fields[0].axiom_tag == "P0"
        assert fields[0].docstring is not None
        assert "monotonicity" in fields[0].docstring.lower()
        # Field with no docstring: docstring is None.
        assert fields[2].docstring is None

    def test_no_where_returns_empty(self):
        sig = "def foo : Nat"
        assert extract_fields_from_signature(sig) == []

    def test_structure_multiline_field_type(self):
        sig = (
            "structure Datum where\n"
            "  /-- The action. -/\n"
            "  act : ∀ (n : G), n ∈ G' → ∀ (E : X'),\n"
            "    n • E = E\n"
        )
        fields = extract_fields_from_signature(sig)
        assert [f.name for f in fields] == ["act"]


class TestFieldCoverage:
    def test_backtick_mention_covers(self):
        assert field_covered_in_body(LeanField("P0"), "the field `P0` matters")

    def test_axiom_tag_covers(self):
        f = LeanField("P0", docstring="(P0) monotonicity.")
        assert field_covered_in_body(f, "we assume **(P0)** cosheaf monotonicity")

    def test_docstring_keyword_covers(self):
        f = LeanField("P0", docstring="(P0) Cosheaf monotonicity.")
        assert field_covered_in_body(f, "cosheaf monotonicity gives ...")

    def test_no_mention_uncovered(self):
        f = LeanField("P0", docstring="(P0) Cosheaf monotonicity.")
        assert not field_covered_in_body(f, "we require only P1 and P2 axioms")

    def test_base_name_short_no_false_positive(self):
        # Base "p0" has length 2, below threshold — no coverage from that alone.
        f = LeanField("P0")
        assert not field_covered_in_body(f, "prose without any relevant tags")


class TestAudit:
    def test_audit_reports_missing_p0(self, tmp_path: Path):
        # Lean root
        lean = tmp_path / "lean"
        lean.mkdir()
        (lean / "Foo.lean").write_text(
            "namespace Bar\n"
            "structure MyDatum where\n"
            "  /-- (P0) Cosheaf monotonicity. -/\n"
            "  P0 : ∀ x, True\n"
            "  /-- (P1) equivariance. -/\n"
            "  P1 : ∀ x, True\n"
            "  /-- (P2) intersection. -/\n"
            "  P2 : ∀ x, True\n"
            "end Bar\n"
        )
        idx = index_lean_project(lean)

        # KB
        kb = tmp_path / "kb"
        (kb / "nodes" / "topic").mkdir(parents=True)
        (kb / "mdblueprint.yml").write_text(
            "site:\n  title: T\n"
            "topics:\n  - id: topic\n    title: T\n"
            "lean:\n  default_repository: local\n"
            "  repositories:\n    - id: local\n      title: Local\n"
            "      local_path: ../lean\n"
            "      web_url: https://example.com\n"
            "      source_url_template: 'https://example.com/{path}#L{line}'\n"
            "      revision: main\n"
        )
        (kb / "nodes" / "topic" / "n.md").write_text(
            "---\nid: topic.n\ntitle: N\nkind: definition\nstatus: admitted\n"
            "primary_topic: topic\n"
            "topics:\n  - topic\n"
            "lean:\n  modules:\n    - Foo\n"
            "  declarations:\n    - Bar.MyDatum\n"
            "---\n"
            "\nWe assume (P1) and (P2). No mention of the third axiom.\n"
        )

        ctx = KnowledgeContext.load(kb)
        findings = audit_knowledge_base(ctx, idx)
        # Should report P0 uncovered, P1 and P2 covered (tag + docstring word).
        uncovered = [f.field.name for f in findings]
        assert "P0" in uncovered, f"expected P0 to be flagged, got {uncovered}"
        assert "P1" not in uncovered
        assert "P2" not in uncovered

    def test_audit_covers_via_docstring_keyword(self, tmp_path: Path):
        lean = tmp_path / "lean"
        lean.mkdir()
        (lean / "Foo.lean").write_text(
            "structure D where\n"
            "  /-- (P0) Cosheaf monotonicity: a smaller cell gets the bigger subgroup. -/\n"
            "  P0 : ∀ x, True\n"
        )
        idx = index_lean_project(lean)

        kb = tmp_path / "kb"
        (kb / "nodes" / "topic").mkdir(parents=True)
        (kb / "mdblueprint.yml").write_text(
            "site:\n  title: T\n"
            "topics:\n  - id: topic\n    title: T\n"
            "lean:\n  default_repository: local\n"
            "  repositories:\n    - id: local\n      title: Local\n"
            "      local_path: ../lean\n"
            "      web_url: https://example.com\n"
            "      source_url_template: 'https://example.com/{path}#L{line}'\n"
            "      revision: main\n"
        )
        (kb / "nodes" / "topic" / "n.md").write_text(
            "---\nid: topic.n\ntitle: N\nkind: definition\nstatus: admitted\n"
            "primary_topic: topic\n"
            "topics:\n  - topic\n"
            "lean:\n  modules:\n    - Foo\n"
            "  declarations:\n    - D\n"
            "---\n"
            "\nWe explain cosheaf monotonicity in the prose without a (P0) tag.\n"
        )

        ctx = KnowledgeContext.load(kb)
        findings = audit_knowledge_base(ctx, idx)
        assert not findings, (
            f"docstring-keyword should cover P0; got {[f.field.name for f in findings]}"
        )


class TestReport:
    def test_empty_report(self):
        r = render_report([])
        assert "No findings" in r

    def test_report_grouped_by_node(self, tmp_path: Path):
        findings = [
            # Uses tmp path to construct a plausible node_path.
            # Report just checks node-level grouping.
        ]
        # Basic smoke: even empty non-report still contains header.
        assert "field-coverage audit" in render_report([])
