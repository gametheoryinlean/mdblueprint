"""Schema tests for multi-candidate proof layout (issue #159, PR 1).

Covers per-node schema rules and the relationship between the four
candidate-related constants:

- ``VALID_STATUSES`` gains ``candidate``, ``promoted``, ``abandoned``.
- ``CANDIDATE_STATUSES`` covers exactly the three new values.
- ``PROOF_BEARING_STATUSES = ADMITTED_STATUSES | {"promoted"}``.
- ``ADMITTED_STATUSES`` is unchanged (no ``promoted``).

Cross-file rules (canonical ↔ candidates statement equality, sibling
promoted-uniqueness, file layout) land in PR 2.
"""
from __future__ import annotations

import pytest

from tools.knowledge.models import (
    ADMITTED_STATUSES,
    CANDIDATE_STATUSES,
    PROOF_BEARING_STATUSES,
    VALID_STATUSES,
)
from tools.knowledge.parser import parse_node
from tools.knowledge.validator import validate_node


_CANDIDATE_TEMPLATE = """---
id: {id}
title: {title}
kind: {kind}
status: {status}
candidate_of: {candidate_of}
candidate_slug: {candidate_slug}
uses: []
verification:
  statement: accepted
  proof: {proof}
---

# {title}

Statement body.

*Proof.* placeholder.
"""

_CANONICAL_MULTI_TEMPLATE = """---
id: {id}
title: {title}
kind: theorem
status: admitted
candidate_layout: {candidate_layout}
promoted_candidate: {promoted_candidate}
candidates: {candidates}
uses: []
verification:
  statement: accepted
  proof: accepted
lean:
  modules: [Lib.M]
  declarations: [Lib.D]
---

# {title}

Statement body.
"""


class TestConstants:
    def test_admitted_statuses_unchanged(self):
        assert ADMITTED_STATUSES == frozenset({"admitted", "formalized", "proved"})

    def test_candidate_statuses(self):
        assert CANDIDATE_STATUSES == frozenset({"candidate", "promoted", "abandoned"})

    def test_proof_bearing_statuses(self):
        assert PROOF_BEARING_STATUSES == ADMITTED_STATUSES | {"promoted"}

    def test_promoted_not_in_admitted(self):
        assert "promoted" not in ADMITTED_STATUSES

    def test_new_statuses_in_valid_set(self):
        assert "candidate" in VALID_STATUSES
        assert "promoted" in VALID_STATUSES
        assert "abandoned" in VALID_STATUSES


class TestCandidateSlug:
    def _candidate_text(self, *, slug: str, status: str = "candidate") -> str:
        return _CANDIDATE_TEMPLATE.format(
            id=f"topic.thm._{slug}",
            title="Thm Candidate",
            kind="theorem",
            status=status,
            candidate_of="topic.thm",
            candidate_slug=slug,
            proof="accepted" if status == "promoted" else "gap",
        )

    @pytest.mark.parametrize("slug", ["cand_a", "cand_z", "cand_1", "a", "x_y_z_99", "ab12_cd"])
    def test_valid_slugs(self, slug):
        node = parse_node(self._candidate_text(slug=slug))
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert errors == [], f"slug {slug!r}: {errors}"

    @pytest.mark.parametrize("slug", ["cand-a", "Cand_A", "cand a", "", "x" * 17, "ab.cd"])
    def test_invalid_slugs(self, slug):
        text = self._candidate_text(slug=slug)
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidate_slug" in msgs, f"slug {slug!r} should fail; got {msgs!r}"


class TestCandidateOfRules:
    def _make(self, **overrides):
        defaults = dict(
            id="topic.thm._cand_a",
            title="Cand A",
            kind="theorem",
            status="candidate",
            candidate_of="topic.thm",
            candidate_slug="cand_a",
            proof="gap",
        )
        defaults.update(overrides)
        return _CANDIDATE_TEMPLATE.format(**defaults)

    def test_candidate_of_requires_slug(self):
        text = self._make(candidate_slug="").replace(
            "candidate_slug: \n", ""  # drop empty value cleanly
        )
        # Re-render without the candidate_slug line entirely.
        text = """---
id: topic.thm._cand_a
title: Cand A
kind: theorem
status: candidate
candidate_of: topic.thm
uses: []
---

# Cand A

Body.

*Proof.* placeholder.
"""
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidate_slug" in msgs

    def test_candidate_of_rejects_non_statement_kind(self):
        node = parse_node(self._make(kind="definition"))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidate" in msgs and "kind" in msgs

    def test_candidate_of_rejects_non_candidate_status(self):
        node = parse_node(self._make(status="admitted"))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "status" in msgs

    def test_candidate_id_must_match_slug_composition(self):
        node = parse_node(self._make(id="topic.thm._cand_b"))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "id" in msgs

    def test_candidate_status_in_nodes_dir_is_allowed(self):
        node = parse_node(self._make(status="candidate"))
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert errors == [], errors

    def test_promoted_status_in_nodes_dir_is_allowed(self):
        node = parse_node(self._make(status="promoted", proof="accepted"))
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        # Promoted candidates do not need a Lean section directly — the
        # canonical owns the Lean ref. Allow missing lean here.
        non_lean_errors = [e for e in errors if "lean" not in e.message.lower()]
        assert non_lean_errors == [], non_lean_errors


class TestCanonicalMultiLayoutRules:
    def _make(self, **overrides):
        defaults = dict(
            id="topic.thm",
            title="Thm",
            candidate_layout="multi",
            promoted_candidate="cand_a",
            candidates="[cand_a]",
        )
        defaults.update(overrides)
        return _CANONICAL_MULTI_TEMPLATE.format(**defaults)

    def test_canonical_multi_accepts_well_formed(self):
        node = parse_node(self._make())
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert errors == [], errors

    def test_candidate_layout_must_equal_multi(self):
        node = parse_node(self._make(candidate_layout="single"))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidate_layout" in msgs

    def test_candidates_must_be_non_empty(self):
        node = parse_node(self._make(candidates="[]"))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidates" in msgs

    def test_promoted_candidate_must_be_in_candidates(self):
        node = parse_node(self._make(
            promoted_candidate="cand_b",
            candidates="[cand_a]",
        ))
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "promoted_candidate" in msgs

    def test_promoted_candidate_null_is_allowed(self):
        node = parse_node(self._make(promoted_candidate="null"))
        diags = validate_node(node, is_staged_dir=False)
        errors = [d for d in diags if d.level == "error"]
        assert errors == [], errors


class TestExclusivity:
    def test_canonical_cannot_also_be_candidate(self):
        text = """---
id: topic.thm._cand_a
title: Hybrid
kind: theorem
status: promoted
candidate_layout: multi
candidate_of: topic.thm
candidate_slug: cand_a
candidates: [cand_a]
promoted_candidate: cand_a
uses: []
verification:
  statement: accepted
  proof: accepted
---

# Hybrid

Body.

*Proof.* placeholder.
"""
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=False)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "candidate" in msgs and ("exclusive" in msgs or "canonical" in msgs)


class TestStagedRejection:
    def test_candidate_of_under_staged_is_rejected(self):
        text = """---
id: topic.thm._cand_a
title: Cand
kind: theorem
status: candidate
candidate_of: topic.thm
candidate_slug: cand_a
uses: []
---

# Cand

Body.

*Proof.* placeholder.
"""
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=True)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "staged" in msgs and "candidate" in msgs

    def test_candidate_layout_under_staged_is_rejected(self):
        text = """---
id: topic.thm
title: Thm
kind: theorem
status: staged
candidate_layout: multi
candidates: [cand_a]
uses: []
---

# Thm

Body.
"""
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=True)
        msgs = " ".join(d.message for d in diags if d.level == "error")
        assert "staged" in msgs and ("candidate_layout" in msgs or "multi-candidate" in msgs)
