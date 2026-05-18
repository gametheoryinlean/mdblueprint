import json
import subprocess
import sys
from pathlib import Path

from tools.knowledge.admission_pipeline import run_admission_pipeline


def _write_definition(path: Path, *, verified: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    verification = "verification:\n  definition: accepted\n" if verified else ""
    path.write_text(
        "---\n"
        "id: algebra.group\n"
        "title: Group\n"
        "kind: definition\n"
        "status: staged\n"
        "uses: []\n"
        f"{verification}"
        "generality:\n  reviewed: true\n"
        "---\n\n"
        "# Group\n",
        encoding="utf-8",
    )


def _write_theorem_with_unverified_proof(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: algebra.identity_unique\n"
        "title: Identity Is Unique\n"
        "kind: theorem\n"
        "status: staged\n"
        "uses: []\n"
        "verification:\n  statement: accepted\n"
        "generality:\n  reviewed: true\n"
        "---\n\n"
        "# Identity Is Unique\n\n*Proof.* Done.\n",
        encoding="utf-8",
    )


def _write_theorem_without_proof(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: algebra.identity_unique\n"
        "title: Identity Is Unique\n"
        "kind: theorem\n"
        "status: staged\n"
        "uses: []\n"
        "verification:\n  statement: accepted\n"
        "generality:\n  reviewed: true\n"
        "---\n\n"
        "# Identity Is Unique\n\nThere is at most one identity element.\n",
        encoding="utf-8",
    )


class TestAdmissionPipeline:
    def test_successful_pipeline_admits_verified_definition(self, tmp_path):
        kb = tmp_path / "knowledge"
        staged = kb / "staged" / "algebra" / "group.md"
        (kb / "nodes").mkdir(parents=True)
        _write_definition(staged)

        result = run_admission_pipeline(staged, kb, require_reviews=False)

        assert result.success
        assert [gate.name for gate in result.gates] == [
            "schema",
            "generality",
            "verification",
            "reviews",
            "dag",
            "write",
        ]
        assert all(gate.status == "passed" for gate in result.gates)
        assert result.target_path is not None
        assert result.target_path.exists()
        assert not staged.exists()

    def test_pipeline_reports_verification_gate_failure(self, tmp_path):
        kb = tmp_path / "knowledge"
        staged = kb / "staged" / "algebra" / "group.md"
        (kb / "nodes").mkdir(parents=True)
        _write_definition(staged, verified=False)

        result = run_admission_pipeline(staged, kb, require_reviews=False)

        assert not result.success
        gate = next(g for g in result.gates if g.name == "verification")
        assert gate.status == "failed"
        assert any("verification.definition" in message for message in gate.messages)
        assert staged.exists()

    def test_pipeline_reports_proof_verification_failure(self, tmp_path):
        kb = tmp_path / "knowledge"
        staged = kb / "staged" / "algebra" / "identity_unique.md"
        (kb / "nodes").mkdir(parents=True)
        _write_theorem_with_unverified_proof(staged)

        result = run_admission_pipeline(staged, kb, require_reviews=False)

        assert not result.success
        gate = next(g for g in result.gates if g.name == "verification")
        assert gate.status == "failed"
        assert any("verification.proof" in message for message in gate.messages)
        assert staged.exists()

    def test_pipeline_blocks_missing_proof_pending_proof_fill(self, tmp_path):
        kb = tmp_path / "knowledge"
        staged = kb / "staged" / "algebra" / "identity_unique.md"
        (kb / "nodes").mkdir(parents=True)
        _write_theorem_without_proof(staged)

        result = run_admission_pipeline(staged, kb, require_reviews=False)

        assert not result.success
        gate = next(g for g in result.gates if g.name == "verification")
        assert gate.status == "failed"
        assert any("proof-fill" in message for message in gate.messages)
        assert result.report_path is not None
        assert result.report_path.exists()
        report = result.report_path.read_text(encoding="utf-8")
        assert "blocked_gate: verification" in report
        assert "proof-fill" in report
        assert staged.exists()

    def test_cli_outputs_json_report(self, tmp_path):
        kb = tmp_path / "knowledge"
        staged = kb / "staged" / "algebra" / "group.md"
        (kb / "nodes").mkdir(parents=True)
        _write_definition(staged)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.knowledge.admission_pipeline",
                str(staged),
                str(kb),
                "--no-reviews",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["success"] is True
        assert data["node_id"] == "algebra.group"
        assert data["report_path"] is None
        assert [gate["name"] for gate in data["gates"]] == [
            "schema",
            "generality",
            "verification",
            "reviews",
            "dag",
            "write",
        ]


def test_admission_pipeline_is_documented():
    docs = [
        Path("README.md").read_text(encoding="utf-8"),
        Path("docs/node-format.md").read_text(encoding="utf-8"),
        Path("docs/agent-contracts.md").read_text(encoding="utf-8"),
        Path("docs/skills.md").read_text(encoding="utf-8"),
    ]
    joined = "\n".join(docs)
    assert "tools.knowledge.admission_pipeline" in joined
    assert "verification.statement" in joined
    assert "verification.definition" in joined
    assert "verification.proof" in joined
    assert "formalized" in joined and "lean.modules" in joined
