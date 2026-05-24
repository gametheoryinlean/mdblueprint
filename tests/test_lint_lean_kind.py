"""Tests for LeanRefKindDetector (PR 5)."""
from __future__ import annotations

from pathlib import Path

from tools.knowledge.graph import build_graph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint import LeanRefKindDetector
from tools.knowledge.models import LeanRef, Node


def _decl(qualified_name: str, kind: str, *, has_sorry: bool = False) -> LeanDeclaration:
    return LeanDeclaration(
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        kind=kind,
        file=Path(f"{qualified_name.replace('.', '/')}.lean"),
        line=1,
        has_sorry=has_sorry,
    )


def _index(decls: list[LeanDeclaration]) -> LeanIndex:
    idx = LeanIndex()
    for d in decls:
        idx.declarations[d.qualified_name] = d
    return idx


def _node(
    node_id: str,
    *,
    kind: str,
    status: str = "formalized",
    lean_decls: list[str] | None = None,
    repository: str | None = None,
) -> Node:
    return Node(
        id=node_id,
        title=node_id,
        kind=kind,
        status=status,
        lean=LeanRef(
            repository=repository,
            modules=["Lib.Mod"],
            declarations=list(lean_decls or []),
        ),
    )


class TestKindMatching:
    def test_theorem_matched_by_lean_theorem_is_silent(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "theorem")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_theorem_with_lean_def_is_a_warning(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.thing"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.thing", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_LEAN_KIND"
        assert d.node_id == "topic.thm"
        assert d.related == ("Lib.thing",)
        assert "theorem" in d.message
        assert "def" in d.message

    def test_definition_matched_by_lean_structure_is_silent(self):
        node = _node("topic.def", kind="definition", lean_decls=["Lib.Group"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.Group", "structure")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_definition_with_lean_theorem_is_a_warning(self):
        node = _node("topic.def", kind="definition", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "theorem")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].code == "LINT_LEAN_KIND"
        assert diags[0].related == ("Lib.proof_x",)

    def test_concept_matches_definition_class(self):
        # `concept` shares the definition kind class.
        node = _node("topic.cpt", kind="concept", lean_decls=["Lib.MyClass"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.MyClass", "class")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_lemma_proposition_external_theorem_all_in_theorem_class(self):
        nodes = [
            _node("topic.lem", kind="lemma", lean_decls=["Lib.x"]),
            _node("topic.prop", kind="proposition", lean_decls=["Lib.y"]),
            _node("topic.ext", kind="external-theorem", lean_decls=["Lib.z"]),
        ]
        graph, _ = build_graph(nodes)
        indexes = {"default": _index([
            _decl("Lib.x", "theorem"),
            _decl("Lib.y", "lemma"),
            _decl("Lib.z", "theorem"),
        ])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run(nodes, graph, llm=None) == []


class TestUnresolvedReferences:
    def test_declaration_missing_from_index_is_skipped_silently(self):
        # Reference resolution failures are check.py's job (lean_check.py
        # already reports them). The lint detector only speaks about kind
        # mismatches and stays silent when there's nothing to compare.
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.does_not_exist"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []


class TestSuffixMatching:
    def test_unqualified_decl_resolves_against_suffix(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.Mod.proof_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        # Even though the declaration was listed unqualified, the kind
        # mismatch is still reported once the suffix match resolves.
        assert len(diags) == 1
        assert diags[0].code == "LINT_LEAN_KIND"

    def test_ambiguous_suffix_match_skips_silently(self):
        # If a short name matches multiple qualified entries, kind comparison
        # is ambiguous; defer to check.py (which reports the ambiguity) and
        # keep the lint detector quiet.
        node = _node("topic.thm", kind="theorem", lean_decls=["proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([
            _decl("Lib.A.proof_x", "def"),
            _decl("Lib.B.proof_x", "theorem"),
        ])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []


class TestRepositoryRouting:
    def test_node_with_explicit_repository_uses_that_index(self):
        node = _node(
            "topic.thm",
            kind="theorem",
            lean_decls=["Lib.proof_x"],
            repository="external",
        )
        graph, _ = build_graph([node])
        indexes = {
            "default": _index([_decl("Lib.proof_x", "def")]),     # would mismatch
            "external": _index([_decl("Lib.proof_x", "theorem")]),  # matches
        }
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_node_without_repository_uses_default(self):
        node = _node(
            "topic.thm",
            kind="theorem",
            lean_decls=["Lib.proof_x"],
            repository=None,
        )
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1


class TestNonMathKindsAreSkipped:
    def test_proof_plan_kind_is_skipped(self):
        node = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
            lean=LeanRef(modules=[], declarations=["Lib.plan_x"]),
        )
        thm = _node("topic.thm", kind="theorem")
        graph, _ = build_graph([thm, node])
        indexes = {"default": _index([_decl("Lib.plan_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        # Proof plans don't carry first-class Lean statement obligations; skip them.
        assert det.run([thm, node], graph, llm=None) == []


class TestNoLeanIndexAvailable:
    def test_none_indexes_emit_single_info(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        det = LeanRefKindDetector(indexes=None)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"
        assert d.code == "LINT_LEAN_KIND"
        assert "lean index not available" in d.message.lower()

    def test_empty_indexes_dict_emit_single_info(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        det = LeanRefKindDetector(indexes={})
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "info"
        assert "lean index not available" in diags[0].message.lower()
