"""Tests for tools.knowledge.refactor_dry_run."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

from tools.knowledge.refactor_dry_run import build_refactor_dry_run


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _write_plan(path: Path, operations: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"operations": operations}, sort_keys=False), encoding="utf-8")


def _make_kb(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    _write(root / "mdblueprint.yml", "site:\n  title: Refactor Dry Run Fixture")
    _write(
        root / "nodes" / "algebra" / "group.md",
        """
        ---
        id: algebra.group
        title: Group
        kind: definition
        status: admitted
        uses: []
        ---

        # Group
        """,
    )
    _write(
        root / "nodes" / "algebra" / "hom.md",
        """
        ---
        id: algebra.group_homomorphism
        title: Group Homomorphism
        kind: definition
        status: admitted
        uses:
          - algebra.group
        ---

        # Group Homomorphism
        """,
    )
    _write(
        root / "nodes" / "algebra" / "iso.md",
        """
        ---
        id: algebra.group_isomorphism
        title: Group Isomorphism
        kind: theorem
        status: admitted
        uses:
          - algebra.group
          - algebra.group_homomorphism
        ---

        # Group Isomorphism
        """,
    )
    return root


def test_refactor_dry_run_removes_dependency_without_writing(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [
        {
            "op": "remove-dependency",
            "node_id": "algebra.group_isomorphism",
            "dependency": "algebra.group",
        }
    ])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is False
    assert result["graph"]["before"]["edges"] == 3
    assert result["graph"]["after"]["edges"] == 2
    assert result["summary"]["changed_node_count"] == 1
    assert result["changed_nodes"][0]["after"]["uses"] == ["algebra.group_homomorphism"]
    assert "algebra.group" in (root / "nodes" / "algebra" / "iso.md").read_text(encoding="utf-8")


def test_refactor_dry_run_detects_cycle_from_added_dependency(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [
        {
            "op": "add-dependency",
            "node_id": "algebra.group",
            "dependency": "algebra.group_isomorphism",
        }
    ])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is True
    assert any("dependency cycle" in diag["message"] for diag in result["new_diagnostics"])


def test_refactor_dry_run_delete_node_surfaces_new_missing_dependencies(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [{"op": "delete-node", "node_id": "algebra.group"}])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is True
    assert result["summary"]["removed_node_count"] == 1
    assert any("dependency not found: 'algebra.group'" in diag["message"] for diag in result["new_diagnostics"])


def test_refactor_dry_run_topic_operations_change_snapshots(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [
        {
            "op": "move-primary-topic",
            "node_id": "algebra.group",
            "topic": "abstract_algebra",
        },
        {
            "op": "add-topic-membership",
            "node_id": "algebra.group",
            "topic": "group_theory",
        },
        {
            "op": "mark-lean-topic-divergent",
            "node_id": "algebra.group",
        },
    ])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is False
    after = result["changed_nodes"][0]["after"]
    assert after["primary_topic"] == "abstract_algebra"
    assert after["explicit_topics"] == ["abstract_algebra", "group_theory"]
    assert after["topic_lean_alignment"] == "divergent"


def test_refactor_dry_run_adds_node_from_request(tmp_path):
    root = _make_kb(tmp_path)
    request = root / "requests" / "inverse.yml"
    _write(
        request,
        """
        request_id: req-inverse
        kind: new-node
        requested_by: graph-refactor-proposer
        created_at: "2026-06-14T00:00:00+00:00"
        target_kind: theorem
        proposed_id: algebra.inverse_unique
        proposed_title: Inverse Is Unique
        summary: Add inverse uniqueness.
        reason: It is reused by several group facts.
        proposed_statement: |
          In a group, each element has at most one inverse.
        proposed_uses:
          - algebra.group
        source_justification: Standard group theory.
        """,
    )
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [{"op": "add-node-from-request", "request_path": "requests/inverse.yml"}])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is False
    assert result["summary"]["added_node_count"] == 1
    added = result["added_nodes"][0]
    assert added["id"] == "algebra.inverse_unique"
    assert added["uses"] == ["algebra.group"]
    assert "each element has at most one inverse" in added["body"]
    assert not (root / "nodes" / "algebra" / "inverse_unique.md").exists()


def test_refactor_dry_run_replace_body_surfaces_unknown_node_ref(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [
        {
            "op": "replace-node-body",
            "node_id": "algebra.group_isomorphism",
            "body": "# Group Isomorphism\n\nThis cites [[node:algebra.missing]].",
        }
    ])

    result = build_refactor_dry_run(root, plan)

    assert result["would_introduce_errors"] is True
    assert result["summary"]["changed_node_count"] == 1
    assert any("unknown node reference [[node:algebra.missing]]" in diag["message"] for diag in result["new_diagnostics"])


def test_refactor_dry_run_cli_outputs_json_and_nonzero_on_errors(tmp_path):
    root = _make_kb(tmp_path)
    plan = tmp_path / "plan.yml"
    _write_plan(plan, [{"op": "add-dependency", "node_id": "algebra.group", "dependency": "missing.node"}])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.refactor_dry_run",
            str(root),
            str(plan),
            "--json",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["operation_diagnostics"][0]["message"] == "operation 1 references unknown dependency 'missing.node'"
