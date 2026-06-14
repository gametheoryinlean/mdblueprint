"""Tests for tools.knowledge.refactor_pack."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.refactor_pack import build_refactor_pack


def _write_node(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _make_kb(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    (root / "mdblueprint.yml").parent.mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Refactor Fixture\n", encoding="utf-8")
    _write_node(
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

        A group is a set with structure.
        """,
    )
    _write_node(
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

        A group homomorphism preserves multiplication.
        """,
    )
    _write_node(
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

        This uses [[node:algebra.group_homomorphism]].
        """,
    )
    _write_node(
        root / "staged" / "algebra" / "ring.md",
        """
        ---
        id: algebra.ring
        title: Ring
        kind: definition
        status: staged
        uses:
          - algebra.group
        ---

        # Ring

        A ring has additive group structure.
        """,
    )
    return root


def test_refactor_pack_target_includes_graph_neighborhood_and_lint(tmp_path):
    root = _make_kb(tmp_path)

    pack = build_refactor_pack(root, target_id="algebra.group_isomorphism")

    assert pack["mode"] == "admitted"
    assert pack["target_id"] == "algebra.group_isomorphism"
    assert pack["focus"]["direct_dependencies"] == [
        "algebra.group",
        "algebra.group_homomorphism",
    ]
    assert pack["focus"]["transitive_ancestors"] == [
        {"node_id": "algebra.group", "distance": 1},
        {"node_id": "algebra.group_homomorphism", "distance": 1},
    ]
    assert "algebra.ring" not in {node["id"] for node in pack["nodes"]}
    assert any(finding["code"] == "LINT_REDUNDANT_DEP" for finding in pack["lint_findings"])

    target = next(node for node in pack["nodes"] if node["id"] == "algebra.group_isomorphism")
    assert target["body_refs"]["refs"] == [
        {
            "target_id": "algebra.group_homomorphism",
            "known": True,
            "in_uses": True,
        }
    ]


def test_refactor_pack_recommends_formulation_review_for_descendants(tmp_path):
    root = _make_kb(tmp_path)

    pack = build_refactor_pack(root, target_id="algebra.group")

    assert pack["formulation_impact"]["review_recommended"] is True
    assert pack["formulation_impact"]["descendant_ids"] == [
        "algebra.group_homomorphism",
        "algebra.group_isomorphism",
    ]
    assert pack["focus"]["direct_dependents"] == [
        "algebra.group_homomorphism",
        "algebra.group_isomorphism",
    ]


def test_refactor_pack_includes_staged_only_when_requested(tmp_path):
    root = _make_kb(tmp_path)

    admitted = build_refactor_pack(root, topic="algebra")
    with_staged = build_refactor_pack(root, topic="algebra", include_staged=True)

    assert "algebra.ring" not in {node["id"] for node in admitted["nodes"]}
    assert admitted["staged_policy"]["included"] is False
    staged = next(node for node in with_staged["nodes"] if node["id"] == "algebra.ring")
    assert staged["evidence"] == "non-admitted"
    assert with_staged["staged_policy"]["included"] is True
    assert with_staged["staged_policy"]["graph_role"].startswith("loaded nodes")


def test_refactor_pack_cli_outputs_json(tmp_path):
    root = _make_kb(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.refactor_pack",
            str(root),
            "--target",
            "algebra.group",
            "--no-lint",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["target_id"] == "algebra.group"
    assert data["lint_findings"] == []
