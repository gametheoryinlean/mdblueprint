"""Tests for the Lean audit coordinator utilities."""
from pathlib import Path

import pytest

from tools.knowledge.config import LeanConfig, LeanRepositoryConfig
from tools.knowledge.lean_audit import (
    LeanAuditError,
    RefCheckerResult,
    RepairClassifierResult,
    build_ref_checker_bundle,
    determine_node_audit_state,
    validate_ref_checker_output,
    validate_repair_classifier_output,
    write_needs_lean_report,
    write_ref_check_report,
    write_repair_report,
)
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.models import LeanRef, Node, Verification


def _node(**kwargs) -> Node:
    defaults = dict(id="t.x", title="X", kind="definition", status="staged", uses=[])
    return Node(**{**defaults, **kwargs})


def _lean_config_with_index(tmp_path: Path) -> tuple[LeanConfig, LeanIndex]:
    lean_path = tmp_path / "lean"
    lean_path.mkdir()
    repo_cfg = LeanRepositoryConfig(
        id="main",
        title="Test Lean",
        local_path=lean_path,
        web_url="https://example.com",
        source_url_template="{web_url}/{path}#L{line}",
        revision="abc123",
    )
    lean_config = LeanConfig(default_repository="main", repositories={"main": repo_cfg})
    decl = LeanDeclaration(
        name="IsGood",
        qualified_name="Ex.IsGood",
        kind="def",
        file=lean_path / "Ex" / "Basic.lean",
        line=1,
        module="Ex.Basic",
    )
    idx = LeanIndex(
        declarations={"Ex.IsGood": decl},
        modules={"Ex.Basic": lean_path / "Ex" / "Basic.lean"},
    )
    return lean_config, idx


class TestDetermineNodeAuditState:
    def test_no_lean_returns_missing_lean(self):
        node = _node(lean=None)
        state = determine_node_audit_state(node, LeanConfig(None, {}), {})
        assert state == "missing_lean"

    def test_unconfigured_repo_returns_lean_ref_broken(self):
        node = _node(lean=LeanRef(repository="nonexistent", modules=["M"], declarations=["M.Foo"]))
        state = determine_node_audit_state(node, LeanConfig(None, {}), {})
        assert state == "lean_ref_broken"

    def test_resolved_ref_returns_pending_alignment(self, tmp_path):
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(lean=LeanRef(repository="main", modules=["Ex.Basic"], declarations=["Ex.IsGood"]))
        state = determine_node_audit_state(node, lean_config, {"main": idx})
        assert state == "pending_alignment"

    def test_resolved_ref_with_aligned_verification_returns_aligned(self, tmp_path):
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(
            lean=LeanRef(repository="main", modules=["Ex.Basic"], declarations=["Ex.IsGood"]),
            verification=Verification(definition="accepted", alignment="aligned"),
        )
        state = determine_node_audit_state(node, lean_config, {"main": idx})
        assert state == "aligned"

    def test_missing_lean_node_is_reported_not_silently_ignored(self):
        node = _node(lean=None)
        state = determine_node_audit_state(node, LeanConfig(None, {}), {})
        assert state == "missing_lean", "nodes without lean: must be explicitly reported"


class TestBuildRefCheckerBundle:
    def test_raises_for_node_without_lean(self, tmp_path):
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(lean=None)
        with pytest.raises(LeanAuditError, match="no lean block"):
            build_ref_checker_bundle(node, lean_config, {"main": idx})

    def test_raises_for_unconfigured_repo(self):
        node = _node(lean=LeanRef(repository="missing", modules=[], declarations=["M.Foo"]))
        with pytest.raises(LeanAuditError, match="not configured"):
            build_ref_checker_bundle(node, LeanConfig(None, {}), {})

    def test_bundle_contains_node_and_declarations(self, tmp_path):
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(lean=LeanRef(repository="main", modules=["Ex.Basic"], declarations=["Ex.IsGood"]))
        bundle = build_ref_checker_bundle(node, lean_config, {"main": idx})
        assert bundle["node"]["id"] == "t.x"
        assert bundle["instructions"]["must_not_write_frontmatter"] is True
        resolved = bundle["resolved_declarations"]
        assert len(resolved) == 1
        assert resolved[0]["declaration"] == "Ex.IsGood"
        assert resolved[0]["status"] == "found"

    def test_bundle_marks_missing_declaration_as_not_found(self, tmp_path):
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(lean=LeanRef(repository="main", modules=["Ex.Basic"], declarations=["Ex.Missing"]))
        bundle = build_ref_checker_bundle(node, lean_config, {"main": idx})
        resolved = bundle["resolved_declarations"]
        assert resolved[0]["status"] == "not_found"


class TestValidateRefCheckerOutput:
    def _valid(self, **kwargs):
        base = {
            "agent": "lean-ref-checker",
            "node_id": "t.x",
            "status": "resolved",
            "declarations": [{"declaration": "Ex.IsGood", "role": "primary_definition"}],
        }
        base.update(kwargs)
        return base

    def test_valid_output_accepted(self):
        result = validate_ref_checker_output(self._valid())
        assert result.node_id == "t.x"
        assert result.status == "resolved"

    def test_wrong_agent_rejected(self):
        with pytest.raises(LeanAuditError, match="agent"):
            validate_ref_checker_output(self._valid(agent="wrong"))

    def test_missing_node_id_rejected(self):
        raw = self._valid()
        raw.pop("node_id")
        with pytest.raises(LeanAuditError, match="node_id"):
            validate_ref_checker_output(raw)

    def test_verification_key_rejected(self):
        with pytest.raises(LeanAuditError, match="verification"):
            validate_ref_checker_output(self._valid(verification={"alignment": "aligned"}))

    def test_lean_key_rejected(self):
        with pytest.raises(LeanAuditError, match="lean"):
            validate_ref_checker_output(self._valid(lean={"modules": ["M"]}))

    def test_invalid_status_rejected(self):
        with pytest.raises(LeanAuditError, match="status"):
            validate_ref_checker_output(self._valid(status="invalid"))

    def test_invalid_role_rejected(self):
        raw = self._valid(declarations=[{"declaration": "Ex.IsGood", "role": "magic"}])
        with pytest.raises(LeanAuditError, match="role"):
            validate_ref_checker_output(raw)

    def test_alignment_reports_do_not_modify_nodes(self):
        # Contract: validation rejects any attempt to write node data
        with pytest.raises(LeanAuditError):
            validate_ref_checker_output(self._valid(verification={"definition": "accepted"}))

    def test_existing_lean_ref_is_checked_before_alignment(self, tmp_path):
        # Ensures the ref checker is invoked for nodes with existing lean: blocks.
        # A node with a broken lean ref must stay in lean_ref_broken, not skip to alignment.
        lean_config, idx = _lean_config_with_index(tmp_path)
        node = _node(lean=LeanRef(repository="main", modules=["Ex.Basic"], declarations=["Ex.Missing"]))
        state = determine_node_audit_state(node, lean_config, {"main": idx})
        assert state == "lean_ref_broken", (
            "nodes with unresolvable lean refs must be checked before alignment"
        )


class TestValidateRepairClassifierOutput:
    def _valid(self, **kwargs):
        base = {
            "agent": "repair-classifier",
            "node_id": "t.x",
            "decision": "small_fix",
            "reason": "module path was incomplete",
        }
        base.update(kwargs)
        return base

    def test_valid_small_fix_accepted(self):
        result = validate_repair_classifier_output(self._valid())
        assert result.decision == "small_fix"

    def test_valid_large_revision_accepted(self):
        result = validate_repair_classifier_output(self._valid(decision="large_revision"))
        assert result.decision == "large_revision"

    def test_patch_key_rejected(self):
        with pytest.raises(LeanAuditError, match="patch"):
            validate_repair_classifier_output(self._valid(patch="--- a\n+++ b\n"))

    def test_diff_key_rejected(self):
        with pytest.raises(LeanAuditError, match="diff"):
            validate_repair_classifier_output(self._valid(diff="--- a\n+++ b\n"))

    def test_statement_field_as_small_fix_rejected(self):
        raw = self._valid(
            decision="small_fix",
            proposed_changes=[{"field": "statement", "description": "reword hypothesis"}],
        )
        with pytest.raises(LeanAuditError, match="large_revision"):
            validate_repair_classifier_output(raw)

    def test_proof_field_as_small_fix_rejected(self):
        raw = self._valid(
            decision="small_fix",
            proposed_changes=[{"field": "proof", "description": "fix proof body"}],
        )
        with pytest.raises(LeanAuditError, match="large_revision"):
            validate_repair_classifier_output(raw)

    def test_uses_field_as_small_fix_rejected(self):
        raw = self._valid(
            decision="small_fix",
            proposed_changes=[{"field": "uses", "description": "add dependency"}],
        )
        with pytest.raises(LeanAuditError, match="large_revision"):
            validate_repair_classifier_output(raw)

    def test_large_revision_with_mathematical_field_accepted(self):
        raw = self._valid(
            decision="large_revision",
            proposed_changes=[{"field": "statement", "description": "reword hypothesis"}],
        )
        result = validate_repair_classifier_output(raw)
        assert result.decision == "large_revision"

    def test_module_path_fix_as_small_fix_accepted(self):
        raw = self._valid(
            decision="small_fix",
            proposed_changes=[{"field": "lean.modules", "description": "correct module path"}],
        )
        result = validate_repair_classifier_output(raw)
        assert result.decision == "small_fix"


class TestWriteReports:
    def test_write_needs_lean_report_creates_file(self, tmp_path):
        path = write_needs_lean_report("t.foo", "no matching declaration", tmp_path)
        assert path.exists()
        content = path.read_text()
        assert "node_id: t.foo" in content
        assert "needs_lean_generation" in content
        assert "no matching declaration" in content

    def test_write_ref_check_report_creates_file(self, tmp_path):
        result = RefCheckerResult(
            node_id="t.x",
            status="broken",
            declarations=[],
            notes="declaration not found",
            raw={"agent": "lean-ref-checker", "node_id": "t.x", "status": "broken"},
        )
        path = write_ref_check_report(result, tmp_path)
        assert path.exists()
        content = path.read_text()
        assert "node_id: t.x" in content
        assert "status: broken" in content

    def test_write_repair_report_creates_file(self, tmp_path):
        result = RepairClassifierResult(
            node_id="t.x",
            decision="large_revision",
            reason="statement needs rewriting",
            raw={
                "agent": "repair-classifier",
                "node_id": "t.x",
                "decision": "large_revision",
                "reason": "statement needs rewriting",
            },
        )
        path = write_repair_report(result, tmp_path)
        assert path.exists()
        content = path.read_text()
        assert "node_id: t.x" in content
        assert "decision: large_revision" in content

    def test_write_needs_lean_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "requests"
        path = write_needs_lean_report("t.x", "reason", nested)
        assert path.exists()
