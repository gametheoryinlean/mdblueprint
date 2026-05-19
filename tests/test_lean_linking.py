import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from tools.knowledge.lean_linking import (
    LeanLinkProposalError,
    apply_lean_link_proposal,
    validate_lean_link_proposal,
    write_link_proposal_report,
)


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


def _knowledge_root(tmp_path: Path) -> Path:
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
    return root


def _proposal(**overrides):
    data = {
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
        "reason": "Lean predicate matches the Markdown definition mechanically.",
        "risks": [],
    }
    data.update(overrides)
    return data


def test_validate_link_proposal_schema_and_mechanical_refs(tmp_path):
    root = _knowledge_root(tmp_path)

    proposal = validate_lean_link_proposal(_proposal(), root)

    assert proposal.node_id == "example.good"
    assert proposal.proposed_lean.declarations == ["Example.IsGood"]


def test_invalid_link_proposal_rejects_alignment_claim(tmp_path):
    root = _knowledge_root(tmp_path)
    raw = _proposal(verification={"alignment": "aligned"})

    with pytest.raises(LeanLinkProposalError, match="alignment"):
        validate_lean_link_proposal(raw, root)


def test_unresolved_link_proposal_is_rejected(tmp_path):
    root = _knowledge_root(tmp_path)
    raw = _proposal(proposed_lean={
        "repository": "main",
        "modules": ["Example.Basic"],
        "declarations": ["Example.Missing"],
    })

    with pytest.raises(LeanLinkProposalError, match="Lean declaration not found"):
        validate_lean_link_proposal(raw, root)


def test_write_report_does_not_modify_node(tmp_path):
    root = _knowledge_root(tmp_path)
    proposal = validate_lean_link_proposal(_proposal(), root)
    node_path = root / "nodes" / "example" / "good.md"
    before = node_path.read_text(encoding="utf-8")

    report = write_link_proposal_report(proposal, root / "reviews")

    assert report.exists()
    assert "decision: link" in report.read_text(encoding="utf-8")
    assert node_path.read_text(encoding="utf-8") == before


def test_apply_validated_link_proposal_updates_only_lean_block(tmp_path):
    root = _knowledge_root(tmp_path)
    proposal = validate_lean_link_proposal(_proposal(), root)
    node_path = root / "nodes" / "example" / "good.md"

    apply_lean_link_proposal(proposal, root)

    text = node_path.read_text(encoding="utf-8")
    assert "lean:" in text
    assert "repository: main" in text
    assert "Example.Basic" in text
    assert "Example.IsGood" in text
    assert "alignment:" not in text
    assert "status: admitted" in text


def test_cli_report_mode_outputs_report_without_apply(tmp_path):
    root = _knowledge_root(tmp_path)
    proposal_path = tmp_path / "proposal.yml"
    proposal_path.write_text(yaml.safe_dump(_proposal()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.knowledge.lean_linking",
            str(root),
            "--proposal",
            str(proposal_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Wrote Lean link proposal report" in result.stdout
    assert "lean:" not in (root / "nodes" / "example" / "good.md").read_text(encoding="utf-8")
