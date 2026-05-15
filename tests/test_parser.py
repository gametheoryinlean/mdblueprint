from pathlib import Path

import pytest

from tools.knowledge.parser import parse_node, parse_file, scan_directory

_TESTS_DIR = Path(__file__).parent
GENERIC_ROOT = _TESTS_DIR / "fixtures" / "generic_knowledge"
GENERIC_NODES_DIR = GENERIC_ROOT / "nodes" / "algebra"
GENERIC_STAGED_DIR = GENERIC_ROOT / "staged" / "algebra"


class TestParseNode:
    def test_parse_generic_definition(self):
        node = parse_file(GENERIC_NODES_DIR / "group.md")
        assert node.id == "algebra.group"
        assert node.title == "Group"
        assert node.kind == "definition"
        assert node.status == "admitted"
        assert node.uses == []
        assert node.lean is not None
        assert "Algebra.Group" in node.lean.declarations
        assert "MyLibrary.Algebra.Group" in node.lean.modules

    def test_parse_source_format(self):
        node = parse_file(GENERIC_NODES_DIR / "group.md")
        assert node.source is not None
        assert len(node.source.artifacts) == 1
        assert node.source.artifacts[0].id == "algebra-text"
        assert "algebra-text" in node.source.artifacts[0].path
        assert len(node.source.spans) == 1
        assert node.source.spans[0].artifact == "algebra-text"
        assert node.source.spans[0].format == "section"

    def test_parse_verification(self):
        node = parse_file(GENERIC_NODES_DIR / "group.md")
        assert node.verification is not None
        assert node.verification.definition == "accepted"
        assert node.verification.statement is None
        assert node.verification.proof == "not_applicable"

    def test_parse_theorem_verification(self):
        node = parse_node(
            "---\n"
            "id: algebra.group_identity_unique\n"
            "title: Group Identity Is Unique\n"
            "kind: theorem\n"
            "status: admitted\n"
            "uses:\n"
            "  - algebra.group\n"
            "verification:\n"
            "  statement: accepted\n"
            "  proof: accepted\n"
            "---\n\n"
            "# Group Identity Is Unique\n\n"
            "A group has a unique identity element.\n"
        )
        assert node.verification is not None
        assert node.verification.statement == "accepted"
        assert node.verification.definition is None
        assert node.verification.proof == "accepted"

    def test_parse_dependencies(self):
        node = parse_file(GENERIC_NODES_DIR / "group_homomorphism.md")
        assert "algebra.group" in node.uses

    def test_parse_lean_repository(self):
        node = parse_node(
            "---\n"
            "id: algebra.group\n"
            "title: Group\n"
            "kind: definition\n"
            "status: admitted\n"
            "uses: []\n"
            "lean:\n"
            "  repository: main\n"
            "  modules:\n"
            "    - MyLibrary.Algebra.Group\n"
            "  declarations:\n"
            "    - Algebra.Group\n"
            "---\n\n"
            "# Group\n"
        )

        assert node.lean is not None
        assert node.lean.repository == "main"

    def test_parse_generality(self):
        node = parse_file(GENERIC_NODES_DIR / "group.md")
        assert node.generality is not None
        assert node.generality.reviewed is True
        assert node.generality.verdict is not None

    def test_parse_body(self):
        node = parse_file(GENERIC_NODES_DIR / "group.md")
        assert "group" in node.body.lower()
        assert "---" not in node.body

    def test_parse_staged(self):
        node = parse_file(GENERIC_STAGED_DIR / "quotient_group.md")
        assert node.status == "staged"
        assert node.verification is None
        assert node.generality is None

    def test_no_frontmatter_raises(self):
        with pytest.raises(ValueError, match="No YAML frontmatter"):
            parse_node("no frontmatter here")

    def test_scan_directory(self):
        nodes = scan_directory(GENERIC_NODES_DIR)
        ids = {n.id for n in nodes}
        assert "algebra.group" in ids
        assert "algebra.group_homomorphism" in ids
        assert len(nodes) == 4
