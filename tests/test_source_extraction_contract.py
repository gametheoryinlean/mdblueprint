from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_extraction_skill_requires_preserving_source_proofs():
    skill = _read("skills/mdblueprint-source-extraction/SKILL.md")

    assert "*Proof.*" in skill
    assert "verification.proof: accepted" in skill
    assert "proof-fill" in skill
    assert "docs/knowledge/requests/" in skill
    assert "admitted + staged" in skill


def test_extraction_report_schema_records_proof_status_and_dependencies():
    schema = _read("skills/mdblueprint-source-extraction/references/extraction-report-schema.md")

    for status in ("full", "partial", "absent", "not_extracted"):
        assert status in schema
    assert "proof_status" in schema
    assert "dependency_alignment" in schema
    assert "missing_dependencies" in schema
    assert "request_path" in schema


def test_project_docs_explain_proof_extraction_contract():
    docs = "\n".join([
        _read("docs/skills.md"),
        _read("docs/agent-contracts.md"),
    ])

    assert "proof-fill" in docs
    assert "*Proof.*" in docs
    assert "proof_status" in docs
    assert "verification.proof: accepted" in docs
