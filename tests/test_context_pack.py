import json
import subprocess
import sys
import textwrap
from pathlib import Path

from tools.knowledge.context_pack import build_context_pack


def _write_node(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def _make_kb(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    (root / "mdblueprint.yml").parent.mkdir(parents=True)
    (root / "mdblueprint.yml").write_text("site:\n  title: Context Fixture\n", encoding="utf-8")
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
        root / "nodes" / "algebra" / "identity.md",
        """
        ---
        id: algebra.identity_unique
        title: Identity Is Unique
        kind: theorem
        status: admitted
        uses:
          - algebra.group
        ---

        # Identity Is Unique

        The identity is unique.
        """,
    )
    _write_node(
        root / "staged" / "algebra" / "inverse.md",
        """
        ---
        id: algebra.inverse_unique
        title: Inverse Is Unique
        kind: theorem
        status: staged
        uses:
          - algebra.group
        ---

        # Inverse Is Unique

        The inverse is unique.
        """,
    )
    return root


def test_context_pack_defaults_to_admitted_nodes_and_dependency_closure(tmp_path):
    root = _make_kb(tmp_path)

    pack = build_context_pack(root, target_id="algebra.identity_unique")

    assert pack["mode"] == "admitted"
    assert pack["forbidden_inputs"] == [
        "Lean source",
        "source artifacts",
        "implementation files",
        "internet",
        "unstated model memory",
    ]
    assert [node["id"] for node in pack["nodes"]] == ["algebra.group", "algebra.identity_unique"]
    assert "algebra.inverse_unique" not in json.dumps(pack)
    assert pack["answer_contract"]["must_cite_node_ids"] is True


def test_context_pack_includes_staged_only_when_explicit(tmp_path):
    root = _make_kb(tmp_path)

    pack = build_context_pack(root, topic="algebra", include_staged=True)

    assert pack["mode"] == "admitted+staged"
    assert any(node["id"] == "algebra.inverse_unique" and node["evidence"] == "non-admitted" for node in pack["nodes"])


def test_context_pack_cli_outputs_json(tmp_path):
    root = _make_kb(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.context_pack",
            str(root),
            "--target",
            "algebra.identity_unique",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["target_id"] == "algebra.identity_unique"
    assert [node["id"] for node in data["nodes"]] == ["algebra.group", "algebra.identity_unique"]
