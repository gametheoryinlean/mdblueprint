"""Tests for tools/knowledge/proof_fill.py.

All tests use fake CodexRunner lambdas — no real API or subprocess calls.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.knowledge.models import Node
from tools.knowledge.proof_fill import (
    GeneratorResult,
    ProofFillReport,
    VerifierResult,
    build_context_bundle,
    decode_generator_output,
    decode_verifier_output,
    insert_proof_into_node,
    run_proof_fill,
    set_verification_proof_accepted,
    validate_generator_result,
    write_failure_report,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_node(
    node_id: str = "math.test",
    title: str = "Test",
    kind: str = "theorem",
    status: str = "needs_proof",
    uses: list[str] | None = None,
    body: str = "Statement body.",
    file_path: Path | None = None,
) -> Node:
    return Node(
        id=node_id,
        title=title,
        kind=kind,
        status=status,
        uses=uses or [],
        body=body,
        tags=[],
        lean=None,
        topics=[],
        primary_topic=None,
        file_path=file_path,
    )


def _gen_json(
    decision: str = "filled",
    proof: str = "By assumption.",
    reason: str = "ok",
    used_node_ids: list[str] | None = None,
) -> str:
    return json.dumps({
        "decision": decision,
        "proof": proof,
        "reason": reason,
        "used_node_ids": used_node_ids or [],
    })


def _ver_json(
    verdict: str = "accepted",
    verification_report: str = "Looks good.",
    gaps: list[str] | None = None,
    critical_errors: list[str] | None = None,
    repair_hint: str = "",
) -> str:
    return json.dumps({
        "verdict": verdict,
        "verification_report": verification_report,
        "gaps": gaps or [],
        "critical_errors": critical_errors or [],
        "repair_hint": repair_hint,
    })


# ── decode_generator_output ───────────────────────────────────────────────────

class TestDecodeGeneratorOutput:
    def test_valid_filled(self):
        raw = _gen_json(decision="filled", proof="By assumption.", used_node_ids=["a.b"])
        result = decode_generator_output(raw)
        assert result.decision == "filled"
        assert result.proof == "By assumption."
        assert result.used_node_ids == ["a.b"]

    def test_valid_cannot_fill(self):
        raw = _gen_json(decision="cannot_fill", proof="", reason="no deps")
        result = decode_generator_output(raw)
        assert result.decision == "cannot_fill"
        assert result.proof == ""

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            decode_generator_output("not json {")

    def test_missing_decision(self):
        with pytest.raises(ValueError, match="missing required field: 'decision'"):
            decode_generator_output(json.dumps({"proof": "x", "reason": "", "used_node_ids": []}))

    def test_missing_proof(self):
        with pytest.raises(ValueError, match="missing required field: 'proof'"):
            decode_generator_output(json.dumps({"decision": "filled", "reason": "", "used_node_ids": []}))

    def test_unknown_decision(self):
        with pytest.raises(ValueError, match="must be 'filled' or 'cannot_fill'"):
            decode_generator_output(_gen_json(decision="maybe"))

    def test_empty_proof_when_filled(self):
        with pytest.raises(ValueError, match="proof text is empty"):
            decode_generator_output(_gen_json(decision="filled", proof="   "))

    def test_placeholder_dots(self):
        with pytest.raises(ValueError, match="placeholders"):
            decode_generator_output(_gen_json(proof="We have ... by induction."))

    def test_placeholder_todo(self):
        with pytest.raises(ValueError, match="placeholders"):
            decode_generator_output(_gen_json(proof="TODO: fill this in"))

    def test_placeholder_insert(self):
        with pytest.raises(ValueError, match="placeholders"):
            decode_generator_output(_gen_json(proof="[insert]"))

    def test_used_node_ids_not_list(self):
        with pytest.raises(ValueError, match="must be a list"):
            decode_generator_output(json.dumps({
                "decision": "filled",
                "proof": "By assumption.",
                "reason": "",
                "used_node_ids": "not-a-list",
            }))


# ── decode_verifier_output ────────────────────────────────────────────────────

class TestDecodeVerifierOutput:
    def test_valid_accepted(self):
        raw = _ver_json(verdict="accepted")
        result = decode_verifier_output(raw)
        assert result.verdict == "accepted"
        assert result.gaps == []
        assert result.critical_errors == []

    def test_valid_gap(self):
        raw = _ver_json(verdict="gap", gaps=["Step 2 unjustified."], repair_hint="Justify step 2.")
        result = decode_verifier_output(raw)
        assert result.verdict == "gap"
        assert result.repair_hint == "Justify step 2."

    def test_valid_critical(self):
        raw = _ver_json(verdict="critical", critical_errors=["Circular reasoning."])
        result = decode_verifier_output(raw)
        assert result.verdict == "critical"
        assert result.critical_errors == ["Circular reasoning."]

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="not valid JSON"):
            decode_verifier_output("broken")

    def test_missing_verdict(self):
        with pytest.raises(ValueError, match="missing required field: 'verdict'"):
            decode_verifier_output(json.dumps({
                "verification_report": "", "gaps": [], "critical_errors": [], "repair_hint": ""
            }))

    def test_unknown_verdict(self):
        with pytest.raises(ValueError, match="must be 'accepted', 'gap', or 'critical'"):
            decode_verifier_output(_ver_json(verdict="unsure"))

    def test_accepted_with_gaps(self):
        with pytest.raises(ValueError, match="non-empty gaps"):
            decode_verifier_output(_ver_json(verdict="accepted", gaps=["oops"]))

    def test_gap_without_gaps(self):
        with pytest.raises(ValueError, match="'gaps' list is empty"):
            decode_verifier_output(_ver_json(verdict="gap", gaps=[]))

    def test_critical_without_errors(self):
        with pytest.raises(ValueError, match="'critical_errors' list is empty"):
            decode_verifier_output(_ver_json(verdict="critical", critical_errors=[]))

    def test_gaps_not_list(self):
        with pytest.raises(ValueError, match="'gaps' must be a list"):
            decode_verifier_output(json.dumps({
                "verdict": "gap", "verification_report": "",
                "gaps": "bad", "critical_errors": [], "repair_hint": ""
            }))


# ── build_context_bundle ──────────────────────────────────────────────────────

class TestBuildContextBundle:
    def test_empty_uses(self):
        node = _make_node(uses=[])
        bundle = build_context_bundle(node, {})
        assert bundle["dependencies"] == []

    def test_dep_included(self):
        dep = _make_node("dep.one", title="Dep One", body="Dep body.")
        node = _make_node(uses=["dep.one"])
        bundle = build_context_bundle(node, {"dep.one": dep})
        assert len(bundle["dependencies"]) == 1
        assert bundle["dependencies"][0]["id"] == "dep.one"
        assert bundle["dependencies"][0]["body"] == "Dep body."

    def test_missing_dep_skipped(self):
        node = _make_node(uses=["missing.dep"])
        bundle = build_context_bundle(node, {})
        assert bundle["dependencies"] == []

    def test_target_frontmatter_contains_id(self):
        node = _make_node(node_id="x.y")
        bundle = build_context_bundle(node, {})
        assert "x.y" in bundle["target_frontmatter"]

    def test_target_body_included(self):
        node = _make_node(body="The statement is P.")
        bundle = build_context_bundle(node, {})
        assert bundle["target_body"] == "The statement is P."

    def test_bundle_has_no_source_material_by_default(self):
        from tools.knowledge.models import Source, SourceArtifact, SourceSpan

        node = _make_node(body="The statement is P.")
        node.source = Source(
            artifacts=[SourceArtifact(id="book", path="references/book.pdf")],
            spans=[SourceSpan(artifact="book", locator="Section 1.2")],
        )
        bundle = build_context_bundle(node, {})
        rendered = json.dumps(bundle)
        assert "references/book.pdf" not in rendered
        assert "Section 1.2" not in rendered
        assert bundle["source_hint"] is None


# ── validate_generator_result ─────────────────────────────────────────────────

class TestValidateGeneratorResult:
    def test_empty_used_ids_ok(self):
        node = _make_node(uses=[])
        result = GeneratorResult("filled", "proof", "ok", [])
        assert validate_generator_result(result, node) is None

    def test_self_citation_ok(self):
        node = _make_node(node_id="math.test", uses=[])
        result = GeneratorResult("filled", "proof", "ok", ["math.test"])
        assert validate_generator_result(result, node) is None

    def test_allowed_dep_ok(self):
        node = _make_node(uses=["dep.a"])
        result = GeneratorResult("filled", "proof", "ok", ["dep.a"])
        assert validate_generator_result(result, node) is None

    def test_disallowed_dep_error(self):
        node = _make_node(uses=["dep.a"])
        result = GeneratorResult("filled", "proof", "ok", ["dep.a", "dep.b"])
        error = validate_generator_result(result, node)
        assert error is not None
        assert "dep.b" in error


# ── run_proof_fill (fake runners) ─────────────────────────────────────────────

class TestRunProofFill:
    """All runners are lambdas; template_dir points to real templates."""

    @pytest.fixture
    def template_dir(self) -> Path:
        return Path(__file__).parent.parent / "tools" / "knowledge" / "templates"

    def _run(self, node, all_nodes, generator, verifier, *, template_dir, **kwargs):
        return run_proof_fill(
            node, all_nodes, generator, verifier,
            template_dir=template_dir, **kwargs
        )

    def test_accepted_on_first_round(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(proof="By assumption."),
            verifier=lambda _: _ver_json(verdict="accepted"),
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "accepted"
        assert report.rounds == 1
        assert report.proof == "By assumption."

    def test_cannot_fill(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(decision="cannot_fill", proof="", reason="too hard"),
            verifier=lambda _: (_ for _ in ()).throw(AssertionError("should not call")),
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "cannot_fill"
        assert report.reason == "too hard"

    def test_critical_stops_immediately(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(proof="Bad proof."),
            verifier=lambda _: _ver_json(verdict="critical", critical_errors=["Circular."]),
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "critical"
        assert "Circular." in report.reason

    def test_gap_then_accepted_on_second_round(self, template_dir):
        calls = {"n": 0}
        def gen(_):
            calls["n"] += 1
            return _gen_json(proof=f"Proof attempt {calls['n']}.")

        def ver(prompt):
            if calls["n"] == 1:
                return _ver_json(verdict="gap", gaps=["Missing step."], repair_hint="Add step X.")
            return _ver_json(verdict="accepted")

        node = _make_node()
        report = self._run(
            node, {},
            generator=gen,
            verifier=ver,
            template_dir=template_dir,
            max_rounds=2,
            dry_run=True,
        )
        assert report.outcome == "accepted"
        assert report.rounds == 2
        assert "Add step X." in report.repair_hints

    def test_gap_exhausted(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(proof="Attempt."),
            verifier=lambda _: _ver_json(verdict="gap", gaps=["Missing."], repair_hint="Fix X."),
            template_dir=template_dir,
            max_rounds=2,
            dry_run=True,
        )
        assert report.outcome == "gap"
        assert report.rounds == 2

    def test_invalid_generator_output(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: "not json at all",
            verifier=lambda _: _ver_json(),
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "invalid_output"

    def test_invalid_verifier_output(self, template_dir):
        node = _make_node()
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(proof="Good proof."),
            verifier=lambda _: "broken verifier output",
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "invalid_output"

    def test_citation_violation(self, template_dir):
        node = _make_node(node_id="math.test", uses=[])
        report = self._run(
            node, {},
            generator=lambda _: _gen_json(proof="Proof.", used_node_ids=["forbidden.dep"]),
            verifier=lambda _: _ver_json(),
            template_dir=template_dir,
            dry_run=True,
        )
        assert report.outcome == "invalid_output"
        assert "forbidden.dep" in report.reason

    def test_dry_run_does_not_write(self, template_dir, tmp_path):
        node_file = tmp_path / "test_node.md"
        node_file.write_text("---\nid: math.test\n---\n\nStatement.\n")
        node = _make_node(file_path=node_file)
        self._run(
            node, {},
            generator=lambda _: _gen_json(proof="By assumption."),
            verifier=lambda _: _ver_json(verdict="accepted"),
            template_dir=template_dir,
            dry_run=True,
        )
        assert "*Proof.*" not in node_file.read_text()


# ── writeback safety ──────────────────────────────────────────────────────────

class TestWritebackSafety:
    def test_insert_proof_appends_block(self, tmp_path):
        f = tmp_path / "node.md"
        f.write_text("---\nid: x\n---\n\nStatement.\n")
        insert_proof_into_node(f, "By induction.")
        assert "*Proof.* By induction." in f.read_text()

    def test_insert_proof_idempotent(self, tmp_path):
        f = tmp_path / "node.md"
        f.write_text("---\nid: x\n---\n\nStatement.\n\n*Proof.* Already there.\n")
        insert_proof_into_node(f, "Should not duplicate.")
        text = f.read_text()
        assert text.count("*Proof.*") == 1

    def test_set_verification_adds_block(self, tmp_path):
        f = tmp_path / "node.md"
        f.write_text("---\nid: x\nstatus: needs_proof\n---\n\nBody.\n")
        set_verification_proof_accepted(f)
        assert "verification:" in f.read_text()
        assert "proof: accepted" in f.read_text()

    def test_set_verification_idempotent(self, tmp_path):
        f = tmp_path / "node.md"
        f.write_text("---\nid: x\nverification:\n  proof: accepted\n---\n\nBody.\n")
        set_verification_proof_accepted(f)
        text = f.read_text()
        assert text.count("proof: accepted") == 1


# ── write_failure_report ──────────────────────────────────────────────────────

class TestWriteFailureReport:
    def _make_report(self, outcome: str = "gap", **kwargs) -> ProofFillReport:
        return ProofFillReport(
            node_id="math.test",
            outcome=outcome,
            proof=None,
            reason="Max rounds reached.",
            rounds=2,
            repair_hints=["Hint 1.", "Hint 2."],
            timestamp="2026-01-01T00:00:00",
            **kwargs,
        )

    def test_report_file_created(self, tmp_path):
        report = self._make_report()
        path = write_failure_report(report, tmp_path / "reviews")
        assert path.exists()

    def test_report_contains_node_id(self, tmp_path):
        report = self._make_report()
        path = write_failure_report(report, tmp_path / "reviews")
        assert "math.test" in path.read_text()

    def test_report_contains_repair_hints(self, tmp_path):
        report = self._make_report()
        path = write_failure_report(report, tmp_path / "reviews")
        assert "Hint 1." in path.read_text()
        assert "Hint 2." in path.read_text()
