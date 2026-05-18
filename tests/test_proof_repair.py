import json
from pathlib import Path

from tools.knowledge.models import Node, Source, SourceArtifact, SourceSpan
from tools.knowledge.parser import parse_file
from tools.knowledge.proof_repair import (
    SourceRecoveryResult,
    find_proof_recovery_candidates,
    run_proof_repair,
)


def _node_file(path: Path, text: str) -> Node:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return parse_file(path)


def _theorem_text(*, proof: str = "", source: bool = True, verification_proof: str | None = None) -> str:
    source_block = (
        "source:\n"
        "  artifacts:\n"
        "    - id: book\n"
        "      path: references/book.pdf\n"
        "  spans:\n"
        "    - artifact: book\n"
        "      locator: Section 1.2\n"
        "      format: section\n"
        if source else ""
    )
    verification = "verification:\n  statement: accepted\n"
    if verification_proof:
        verification += f"  proof: {verification_proof}\n"
    return (
        "---\n"
        "id: algebra.identity_unique\n"
        "title: Identity Is Unique\n"
        "kind: theorem\n"
        "status: staged\n"
        "uses:\n"
        "  - algebra.group\n"
        f"{source_block}"
        f"{verification}"
        "---\n\n"
        "# Identity Is Unique\n\n"
        "There is at most one identity element.\n"
        f"{proof}"
    )


def _dep() -> Node:
    return Node(id="algebra.group", title="Group", kind="definition", status="admitted", body="A group has an identity.")


def _gen_json(proof: str = "By the explicit source hint and algebra.group, the identity is unique.") -> str:
    return json.dumps({
        "decision": "filled",
        "proof": proof,
        "reason": "local",
        "used_node_ids": ["algebra.group"],
    })


def _ver_json() -> str:
    return json.dumps({
        "verdict": "accepted",
        "verification_report": "valid",
        "gaps": [],
        "critical_errors": [],
        "repair_hint": "",
    })


def test_candidate_finder_lists_theorem_like_missing_proof_with_source(tmp_path):
    root = tmp_path / "knowledge"
    target = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text())
    _node_file(
        root / "staged" / "algebra" / "already_done.md",
        _theorem_text(proof="\n\n*Proof.* Done.\n", verification_proof="accepted").replace(
            "algebra.identity_unique", "algebra.already_done"
        ),
    )
    _node_file(
        root / "staged" / "algebra" / "no_source.md",
        _theorem_text(source=False).replace("algebra.identity_unique", "algebra.no_source"),
    )

    candidates = find_proof_recovery_candidates(root)

    assert [node.id for node in candidates] == [target.id]


def test_source_proof_recovery_runs_before_proof_fill(tmp_path):
    root = tmp_path / "knowledge"
    node = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text())
    calls: list[str] = []

    def recover(target, all_nodes):
        calls.append("recover")
        return SourceRecoveryResult(
            decision="recovered",
            proof="The cited source proves uniqueness from the group identity axioms.",
            reason="source proof found",
            used_node_ids=["algebra.group"],
        )

    def generator(prompt):
        calls.append("proof-fill")
        return _gen_json()

    result = run_proof_repair(
        node,
        {"algebra.group": _dep(), node.id: node},
        knowledge_root=root,
        source_recoverer=recover,
        generator=generator,
        verifier=lambda prompt: _ver_json(),
    )

    assert result.outcome == "source_recovered"
    assert calls == ["recover"]
    updated = node.file_path.read_text(encoding="utf-8")
    assert "*Proof.* The cited source proves uniqueness" in updated
    assert "proof: accepted" not in updated
    assert result.source_report_path is not None
    assert "decision: recovered" in result.source_report_path.read_text(encoding="utf-8")


def test_source_hint_is_passed_to_bounded_proof_fill(tmp_path):
    root = tmp_path / "knowledge"
    node = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text())
    prompts: list[str] = []

    def recover(target, all_nodes):
        return SourceRecoveryResult(
            decision="hint_only",
            hint="Use cancellation after comparing the two identity elements.",
            reason="source contains a hint",
        )

    def generator(prompt):
        prompts.append(prompt)
        return _gen_json()

    result = run_proof_repair(
        node,
        {"algebra.group": _dep(), node.id: node},
        knowledge_root=root,
        source_recoverer=recover,
        generator=generator,
        verifier=lambda prompt: _ver_json(),
    )

    assert result.outcome == "proof_fill_accepted"
    assert "Use cancellation" in prompts[0]
    assert "references/book.pdf" not in prompts[0]
    updated = node.file_path.read_text(encoding="utf-8")
    assert "*Proof.* By the explicit source hint" in updated
    assert "proof: accepted" in updated


def test_no_source_uses_proof_fill_fallback_without_recovery(tmp_path):
    root = tmp_path / "knowledge"
    node = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text(source=False))
    calls: list[str] = []

    def recover(target, all_nodes):
        calls.append("recover")
        raise AssertionError("source recovery should not run without source spans")

    def generator(prompt):
        calls.append("proof-fill")
        return _gen_json()

    result = run_proof_repair(
        node,
        {"algebra.group": _dep(), node.id: node},
        knowledge_root=root,
        source_recoverer=recover,
        generator=generator,
        verifier=lambda prompt: _ver_json(),
    )

    assert result.outcome == "proof_fill_accepted"
    assert calls == ["proof-fill"]


def test_recovery_and_fill_failure_writes_reports(tmp_path):
    root = tmp_path / "knowledge"
    node = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text())

    def recover(target, all_nodes):
        return SourceRecoveryResult(decision="not_found", reason="source has no usable proof")

    def generator(prompt):
        return json.dumps({
            "decision": "cannot_fill",
            "proof": "",
            "reason": "needs a missing lemma",
            "used_node_ids": [],
        })

    result = run_proof_repair(
        node,
        {"algebra.group": _dep(), node.id: node},
        knowledge_root=root,
        source_recoverer=recover,
        generator=generator,
        verifier=lambda prompt: _ver_json(),
    )

    assert result.outcome == "blocked"
    assert result.source_report_path is not None
    assert result.proof_fill_report_path is not None
    assert result.source_report_path.exists()
    assert result.proof_fill_report_path.exists()


def test_missing_dependency_from_source_recovery_writes_request(tmp_path):
    root = tmp_path / "knowledge"
    node = _node_file(root / "staged" / "algebra" / "identity_unique.md", _theorem_text())

    def recover(target, all_nodes):
        return SourceRecoveryResult(
            decision="partial",
            proof="The source reduces the proof to a cancellation lemma.",
            reason="missing reusable dependency",
            missing_dependencies=["left cancellation for identities"],
        )

    result = run_proof_repair(
        node,
        {"algebra.group": _dep(), node.id: node},
        knowledge_root=root,
        source_recoverer=recover,
        generator=lambda prompt: _gen_json(),
        verifier=lambda prompt: _ver_json(),
    )

    assert result.outcome == "source_recovered"
    assert result.request_paths
    request = result.request_paths[0].read_text(encoding="utf-8")
    assert "left cancellation for identities" in request
    assert "missing-dependency" in request
