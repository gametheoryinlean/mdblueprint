from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_source_proof_recovery_skill_contract_exists():
    skill = _read("skills/mdblueprint-source-proof-recovery/SKILL.md")

    assert "name: mdblueprint-source-proof-recovery" in skill
    assert "Use when" in skill
    assert "source.spans" in skill
    assert "decision: recovered | partial | hint_only | not_found | blocked" in skill
    assert "verification.proof: accepted" in skill
    assert "proof-fill" in skill
    assert "docs/knowledge/requests/" in skill
    assert "cited source spans" in skill


def test_docs_list_source_proof_recovery_separately():
    docs = "\n".join([
        _read("docs/skills.md"),
        _read("docs/agent-contracts.md"),
        _read("skills/README.md"),
    ])

    assert "mdblueprint-source-proof-recovery" in docs
    assert "source proof recovery" in docs.lower()
    assert "proof-fill" in docs
    assert "proof review" in docs.lower()
    assert "admission" in docs.lower()


def test_proof_fill_docs_allow_only_explicit_source_hint():
    docs = "\n".join([
        _read("skills/mdblueprint-proof-fill/SKILL.md"),
        _read("tools/knowledge/templates/proof_fill_generate.md"),
        _read("docs/agent-contracts.md"),
    ])

    assert "source hint" in docs.lower()
    assert "must not read source files" in docs.lower()
    assert "orchestrator" in docs.lower()
