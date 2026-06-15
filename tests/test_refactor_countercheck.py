from __future__ import annotations

import json
from pathlib import Path

from tools.knowledge.refactor_countercheck import build_refactor_countercheck_run


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node(
    root: Path,
    node_id: str,
    *,
    uses: list[str] | None = None,
    lean: bool = False,
) -> Path:
    lean_block = ""
    if lean:
        lean_block = """lean:
  modules:
    - Example.Algebra
  declarations:
    - Example.Group
"""
    return _write(
        root / "nodes" / "algebra" / f"{node_id.split('.')[-1]}.md",
        f"""---
id: {node_id}
title: {node_id.split('.')[-1].replace('_', ' ').title()}
kind: definition
status: admitted
uses:
{''.join(f'  - {dep}\n' for dep in (uses or [])) if uses else '  []\n'}{lean_block}verification:
  definition: accepted
  proof: not_applicable
---

# {node_id}

Test node.
""",
    )


def _report(path: Path, knowledge_root: Path) -> Path:
    return _write(
        path,
        f"""---
agent: graph-refactor-proposer
target:
  knowledge_root: {knowledge_root}
decision: proposals
created_at: "2026-06-15T00:00:00Z"
inputs:
  - baseline/check.txt
summary: Test refactor report.
baseline:
  check: passed
  lint: findings
  stats: collected
formulation_impact:
  reviewed: true
  reason: Semantic candidates can affect descendants.
---

## Scope

Test scope.

## Deterministic Baseline

Baseline collected.

## Proposals

| proposal_id | kind | classification | targets | action | evidence | risk | validation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| refactor-001 | formulation-impact-review | semantic-review | node:algebra.group | Review formulation. | node:algebra.group | Semantic risk. | Run countercheck. |

## Refinement Pass

Semantic candidate retained.

## Generality Gate

The general form is reviewed.

## Formulation-Sensitive Impact

Descendant impact reviewed.

## Request Files

None.

## Human Decisions

Review final adjudication.
""",
    )


def test_refactor_countercheck_scaffold_generates_pairs_and_skips(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge"
    _node(knowledge_root, "algebra.group", lean=True)
    _node(knowledge_root, "algebra.group_hom", uses=[])
    report = _report(tmp_path / "report.md", knowledge_root)
    plan = _write(
        tmp_path / "plan.yml",
        """operations:
  - op: add-dependency
    node_id: algebra.group_hom
    dependency: algebra.group
""",
    )
    lean_root = tmp_path / "lean"
    _write(
        lean_root / "Example" / "Algebra.lean",
        """def Example.Group : True := by
  trivial
""",
    )

    result = build_refactor_countercheck_run(
        knowledge_root=knowledge_root,
        lean_source_root=lean_root,
        output_root=tmp_path / "runs",
        refactor_report=report,
        dry_run_plan=plan,
        timestamp="20260615T000000Z",
    )

    run_dir = Path(result["run_dir"])
    assert run_dir.name == "20260615T000000Z"
    assert result["candidate_count"] == 2
    assert result["pair_count"] == 1
    assert result["skipped_count"] == 1
    assert result["countercheck_ran"] is True

    pairs = json.loads((run_dir / "countercheck" / "pairs.json").read_text())
    skipped = json.loads((run_dir / "countercheck" / "skipped.json").read_text())
    counter_summary = json.loads((run_dir / "countercheck" / "summary.json").read_text())

    assert pairs[0]["node_id"] == "algebra.group"
    assert pairs[0]["sources"] == ["refactor-report"]
    assert skipped[0]["node_id"] == "algebra.group_hom"
    assert skipped[0]["reason"] == "node has no lean metadata"
    assert counter_summary["pairs"] == 1
    assert (run_dir / "prompts" / "adjudicator.md").exists()
    assert (run_dir / "scripts" / "run-adjudicator.sh").exists()


def test_refactor_countercheck_prepare_only_writes_timestamped_layout(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "knowledge"
    _node(knowledge_root, "algebra.group", lean=True)

    result = build_refactor_countercheck_run(
        knowledge_root=knowledge_root,
        lean_source_root=tmp_path / "lean",
        output_root=tmp_path / "runs",
        timestamp="20260615T010000Z",
        prepare_only=True,
    )

    run_dir = Path(result["run_dir"])
    assert result["prepare_only"] is True
    assert result["candidate_count"] == 0
    assert (run_dir / "metadata.json").exists()
    assert (run_dir / "countercheck" / "pairs.json").exists()
    assert (run_dir / "SUMMARY.md").exists()
