import subprocess
import textwrap
from pathlib import Path

import pytest

from tools.knowledge.lean_alignment import (
    LeanAlignmentError,
    build_alignment_bundle,
    validate_alignment_report,
    write_alignment_report,
)
from tools.knowledge.lean_linking import apply_lean_link_proposal, validate_lean_link_proposal


def _init_lean_repo(path: Path) -> str:
    (path / "Example").mkdir(parents=True)
    (path / "Example" / "Basic.lean").write_text(
        "namespace Example\n\ndef IsGood (n : Nat) : Prop := n = n\n\nend Example\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


def _root(tmp_path: Path) -> Path:
    lean_root = tmp_path / "lean"
    commit = _init_lean_repo(lean_root)
    root = tmp_path / "knowledge"
    (root / "nodes" / "example").mkdir(parents=True)
    (root / "mdblueprint.yml").write_text(
        textwrap.dedent(f"""
        site:
          title: Test KB
        lean:
          default_repository: main
          repositories:
            - id: main
              title: Private Lean
              local_path: {lean_root}
              web_url: https://github.com/org/private-lean
              source_url_template: "{{web_url}}/blob/{{revision}}/{{path}}#L{{line}}"
              revision: {commit}
        """).strip() + "\n",
        encoding="utf-8",
    )
    (root / "nodes" / "example" / "good.md").write_text(
        textwrap.dedent("""
        ---
        id: example.good
        title: Good
        kind: definition
        status: admitted
        uses: []
        verification:
          definition: accepted
        ---

        # Good

        A good natural number satisfies the predicate.
        """).strip() + "\n",
        encoding="utf-8",
    )
    proposal = validate_lean_link_proposal({
        "agent": "lean-linking",
        "node_id": "example.good",
        "decision": "link",
        "proposed_lean": {
            "repository": "main",
            "modules": ["Example.Basic"],
            "declarations": ["Example.IsGood"],
        },
        "primary_declaration": "Example.IsGood",
        "role_notes": {"Example.IsGood": "primary_definition"},
        "reason": "mechanical",
        "risks": [],
    }, root)
    apply_lean_link_proposal(proposal, root)
    return root


def _report(**overrides):
    raw = {
        "agent": "alignment-verifier",
        "node_id": "example.good",
        "repository": "main",
        "declaration": "Example.IsGood",
        "classification": "aligned",
        "evidence": [
            {
                "markdown": "good natural number satisfies the predicate",
                "lean": "def IsGood (n : Nat) : Prop",
                "note": "both describe the same predicate",
            }
        ],
        "risks": [],
        "recommendation": "set verification.alignment to aligned after human gate",
    }
    raw.update(overrides)
    return raw


def test_build_alignment_bundle_is_bounded(tmp_path):
    root = _root(tmp_path)

    bundle = build_alignment_bundle(root, "example.good", "Example.IsGood")

    assert bundle["node"]["id"] == "example.good"
    assert bundle["lean_declaration"]["declaration"] == "Example.IsGood"
    assert "def IsGood" in bundle["lean_declaration"]["signature"]
    assert "source_url" in bundle["lean_declaration"]
    assert bundle["instructions"]["agent_must_not_write_frontmatter"] is True


def test_validate_alignment_report_accepts_structured_evidence(tmp_path):
    root = _root(tmp_path)

    report = validate_alignment_report(_report(), root)

    assert report.classification == "aligned"
    assert report.declaration == "Example.IsGood"


def test_validate_alignment_report_rejects_missing_evidence(tmp_path):
    root = _root(tmp_path)

    with pytest.raises(LeanAlignmentError, match="evidence"):
        validate_alignment_report(_report(evidence=[]), root)


def test_validate_alignment_report_rejects_unresolved_declaration(tmp_path):
    root = _root(tmp_path)

    with pytest.raises(LeanAlignmentError, match="Lean declaration not found"):
        validate_alignment_report(_report(declaration="Example.Missing"), root)


def test_write_alignment_report_does_not_modify_node(tmp_path):
    root = _root(tmp_path)
    report = validate_alignment_report(_report(classification="lean_weaker"), root)
    node_path = root / "nodes" / "example" / "good.md"
    before = node_path.read_text(encoding="utf-8")

    report_path = write_alignment_report(report, root / "reviews")

    assert report_path.exists()
    assert "classification: lean_weaker" in report_path.read_text(encoding="utf-8")
    assert node_path.read_text(encoding="utf-8") == before
