"""Tests for tools.knowledge.refactor_report_check."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.refactor_report_check import check_refactor_report


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _make_kb(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    _write(root / "mdblueprint.yml", "site:\n  title: Refactor Report Fixture")
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


def _valid_report(root: Path) -> str:
    return f"""
    ---
    agent: graph-refactor-proposer
    target:
      knowledge_root: {root}
      node_id: algebra.group_isomorphism
    decision: proposals
    created_at: "2026-06-14T00:00:00+00:00"
    inputs:
      - uv run python -m tools.knowledge.refactor_pack {root} --target algebra.group_isomorphism
    summary: Remove one redundant dependency edge.
    baseline:
      check: passed
      lint: findings
      stats: collected
    formulation_impact:
      reviewed: true
      reason: Removing a redundant dependency edge changes graph structure but not node text.
    ---

    ## Scope

    Target node `algebra.group_isomorphism`; admitted nodes only.

    ## Deterministic Baseline

    `check` passed and lint reported `LINT_REDUNDANT_DEP`.

    ## Proposals

    | proposal_id | kind | classification | targets | action | evidence | risk | validation |
    | --- | --- | --- | --- | --- | --- | --- | --- |
    | refactor-001 | remove-redundant-dependency | mechanical-safe | algebra.group_isomorphism, algebra.group | Remove `algebra.group` from `uses`. | `LINT_REDUNDANT_DEP`; algebra.group_homomorphism uses algebra.group | The edge may encode a deliberate direct formulation dependency. | `uv run python -m tools.knowledge.check docs/knowledge` |

    ## Generality Gate

    Not applicable; no merge, split, generalization, or rehome is proposed.

    ## Formulation-Sensitive Impact

    Direct formulation impact is reviewed; no node body is changed.

    ## Request Files

    Not applicable.

    ## Human Decisions

    None.
    """


def test_refactor_report_check_accepts_valid_report(tmp_path):
    root = _make_kb(tmp_path)
    report = root / "reviews" / "refactor.md"
    _write(report, _valid_report(root))

    diags = check_refactor_report(report, root)

    assert [diag for diag in diags if diag.level == "error"] == []


def test_refactor_report_check_rejects_unknown_target_ids(tmp_path):
    root = _make_kb(tmp_path)
    report = root / "reviews" / "refactor.md"
    _write(report, _valid_report(root).replace("algebra.group", "algebra.missing"))

    diags = check_refactor_report(report, root)

    assert any("unknown node/topic id 'algebra.missing'" in diag.message for diag in diags)


def test_refactor_report_check_requires_formulation_review_for_dependency_changes(tmp_path):
    root = _make_kb(tmp_path)
    report = root / "reviews" / "refactor.md"
    _write(report, _valid_report(root).replace("reviewed: true", "reviewed: false"))

    diags = check_refactor_report(report, root)

    assert any("formulation_impact.reviewed must be true" in diag.message for diag in diags)


def test_refactor_report_check_rejects_invalid_proposal_kind(tmp_path):
    root = _make_kb(tmp_path)
    report = root / "reviews" / "refactor.md"
    _write(
        report,
        _valid_report(root).replace("remove-redundant-dependency", "rewrite-the-kb"),
    )

    diags = check_refactor_report(report, root)

    assert any("invalid kind 'rewrite-the-kb'" in diag.message for diag in diags)


def test_refactor_report_check_cli_returns_nonzero_for_errors(tmp_path):
    root = _make_kb(tmp_path)
    report = root / "reviews" / "refactor.md"
    _write(report, _valid_report(root).replace("agent: graph-refactor-proposer", "agent: other"))

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.refactor_report_check",
            str(root),
            str(report),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "agent must be 'graph-refactor-proposer'" in result.stdout
