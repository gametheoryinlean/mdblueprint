"""Tests for tools/knowledge/node_refs.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.models import Node
from tools.knowledge.node_refs import (
    NODE_REF_RE,
    check_node_body_refs,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _node(
    node_id: str = "topic.node",
    title: str = "A Node",
    kind: str = "definition",
    uses: list[str] | None = None,
    body: str = "",
    file_path: Path | None = None,
) -> Node:
    return Node(
        id=node_id, title=title, kind=kind, status="admitted",
        uses=uses or [], body=body, tags=[], lean=None,
        topics=[], primary_topic=None, file_path=file_path,
    )


def _index(*nodes: Node) -> dict[str, Node]:
    return {n.id: n for n in nodes}


# ── NODE_REF_RE ────────────────────────────────────────────────────────────────

class TestNodeRefRegex:
    def test_simple_ref(self):
        m = NODE_REF_RE.search("See [[node:math.lemma]] here.")
        assert m is not None
        assert m.group(1) == "math.lemma"
        assert m.group(2) is None

    def test_ref_with_label(self):
        m = NODE_REF_RE.search("[[node:math.lemma|the lemma]]")
        assert m is not None
        assert m.group(1) == "math.lemma"
        assert m.group(2) == "the lemma"

    def test_nested_topic(self):
        m = NODE_REF_RE.search("[[node:a.b.c.theorem]]")
        assert m is not None
        assert m.group(1) == "a.b.c.theorem"

    def test_no_match_bare_word(self):
        assert NODE_REF_RE.search("some word") is None

    def test_no_match_missing_node_prefix(self):
        assert NODE_REF_RE.search("[[math.lemma]]") is None

    def test_no_match_uppercase(self):
        assert NODE_REF_RE.search("[[node:Math.Lemma]]") is None

    def test_multiple_refs(self):
        text = "[[node:a.x]] and [[node:b.y|B]]"
        matches = list(NODE_REF_RE.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "a.x"
        assert matches[1].group(1) == "b.y"
        assert matches[1].group(2) == "B"


# ── check_node_body_refs ───────────────────────────────────────────────────────

class TestUnknownNodeRef:
    def test_unknown_id_produces_error(self):
        node = _node(body="See [[node:missing.id]] here.")
        diags = check_node_body_refs(node, {})
        assert any(d.level == "error" and "missing.id" in d.message for d in diags)

    def test_known_id_no_error(self):
        target = _node("topic.dep")
        node = _node(body="See [[node:topic.dep]].")
        diags = check_node_body_refs(node, _index(target))
        errors = [d for d in diags if d.level == "error"]
        assert errors == []

    def test_multiple_refs_one_unknown(self):
        target = _node("topic.dep")
        node = _node(body="[[node:topic.dep]] and [[node:topic.missing]].")
        diags = check_node_body_refs(node, _index(target))
        errors = [d for d in diags if d.level == "error"]
        assert len(errors) == 1
        assert "topic.missing" in errors[0].message


class TestProofRefNotInUses:
    """Theorem-like nodes: proof [[node:id]] not in uses → warning."""

    def test_proof_ref_in_uses_no_warning(self):
        dep = _node("dep.x")
        node = _node(kind="theorem", uses=["dep.x"], body="Stmt.\n\n*Proof.* By [[node:dep.x]]. $\\square$")
        diags = check_node_body_refs(node, _index(dep))
        warnings = [d for d in diags if d.level == "warning" and "dep.x" in d.message]
        assert warnings == []

    def test_proof_ref_not_in_uses_warning(self):
        dep = _node("dep.x")
        node = _node(kind="theorem", uses=[], body="Stmt.\n\n*Proof.* By [[node:dep.x]]. $\\square$")
        diags = check_node_body_refs(node, _index(dep))
        warnings = [d for d in diags if d.level == "warning" and "dep.x" in d.message]
        assert len(warnings) == 1

    def test_statement_ref_not_in_uses_no_warning(self):
        dep = _node("dep.x")
        node = _node(kind="theorem", uses=[], body="By [[node:dep.x]] the result holds.")
        diags = check_node_body_refs(node, _index(dep))
        warnings = [d for d in diags if "dep.x" in d.message and d.level == "warning"]
        assert warnings == []

    def test_non_theorem_kind_no_warning(self):
        dep = _node("dep.x")
        node = _node(kind="definition", uses=[], body="Defn.\n\n*Proof.* By [[node:dep.x]]. $\\square$")
        diags = check_node_body_refs(node, _index(dep))
        warnings = [d for d in diags if "dep.x" in d.message and d.level == "warning"]
        assert warnings == []

    def test_proposition_kind_triggers_warning(self):
        dep = _node("dep.x")
        node = _node(kind="proposition", uses=[], body="Stmt.\n\n*Proof.* By [[node:dep.x]]. $\\square$")
        diags = check_node_body_refs(node, _index(dep))
        warnings = [d for d in diags if d.level == "warning" and "dep.x" in d.message]
        assert len(warnings) == 1


class TestNakedSourceLocalRefs:
    def test_lemma_number_triggers_warning(self):
        node = _node(body="By Lemma 6.2, the result follows.")
        diags = check_node_body_refs(node, {})
        assert any("Lemma 6.2" in d.message and d.level == "warning" for d in diags)

    def test_theorem_number_triggers_warning(self):
        node = _node(body="See Theorem 8.1.2 for details.")
        diags = check_node_body_refs(node, {})
        assert any("Theorem 8.1.2" in d.message for d in diags)

    def test_no_warning_for_plain_text(self):
        node = _node(body="A simple statement with no references.")
        diags = check_node_body_refs(node, {})
        assert diags == []

    def test_no_warning_for_node_ref(self):
        dep = _node("topic.dep")
        node = _node(body="By [[node:topic.dep]].")
        diags = check_node_body_refs(node, _index(dep))
        assert diags == []

    def test_no_naked_ref_on_standalone_lemma_word(self):
        node = _node(body="This is a lemma about groups.")
        diags = check_node_body_refs(node, {})
        naked = [d for d in diags if "ambiguous source-local" in d.message]
        assert naked == []
