from pathlib import Path


ROOT = Path(__file__).parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_lean_linking_skill_exists_and_separates_alignment():
    skill = _read("skills/mdblueprint-lean-linking/SKILL.md")

    assert "name: mdblueprint-lean-linking" in skill
    assert "Codex, Claude, OpenCode" in skill
    assert "decision: link | no_match | ambiguous | needs_lean_generation | needs_human_decision" in skill
    assert "proposed_lean:" in skill
    assert "mechanical link" in skill
    assert "verification.alignment" in skill
    assert "status: formalized" in skill


def test_alignment_skill_schema_is_bounded_and_structured():
    skill = _read("skills/mdblueprint-alignment-review/SKILL.md")
    schema = _read("skills/mdblueprint-alignment-review/references/alignment-report-schema.md")

    assert "bounded" in skill.lower()
    assert "must not scan" in skill.lower()
    assert "classification:" in schema
    assert "evidence:" in schema
    assert "lean_extra_hypotheses" in schema
    assert "definition_mismatch" in schema
    assert "verification.alignment" in skill


def test_private_lean_repo_docs_have_security_contract():
    docs = "\n".join([
        _read("docs/lean-repositories.md"),
        _read("docs/github-integration.md"),
    ])

    assert "private" in docs.lower()
    assert "source_url_template" in docs
    assert "revision: auto" in docs
    assert "tokens" in docs.lower() or "secrets" in docs.lower()
    assert "GitHub permissions" in docs


def test_skill_maps_include_lean_linking():
    docs = "\n".join([
        _read("README.md"),
        _read("docs/skills.md"),
        _read("skills/README.md"),
        _read("docs/agent-contracts.md"),
    ])

    assert "mdblueprint-lean-linking" in docs
    assert "lean_link_candidates" in docs
    assert "lean_linking" in docs
    assert "lean_alignment" in docs
