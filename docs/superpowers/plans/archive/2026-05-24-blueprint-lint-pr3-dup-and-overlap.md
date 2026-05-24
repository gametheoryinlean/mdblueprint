# Blueprint Lint PR 3 — Detectors 1 + 2 (fuzzy title/statement dup + staged ↔ admitted overlap) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first two real detectors in `mdblueprint-lint`:

- `FuzzyTitleDupDetector` (code `LINT_FUZZY_DUP`) — flags admitted node pairs whose normalized titles or statements are near-duplicates (default ratio threshold `0.92`).
- `StagedAdmittedOverlapDetector` (code `LINT_STAGED_OVERLAP`) — same normalization and ratio, but restricted to (staged × admitted) cross-pairs so a candidate that silently re-states an already-admitted node surfaces before review.

Both are pure-Python deterministic detectors (no LLM, no extra dependencies). The threshold is configurable via `mdblueprint.yml → lint.fuzzy_threshold`. After this PR, `mdblueprint-lint docs/knowledge` continues to exit 0 on the bundled example (zero false positives at the default threshold), and a focused fixture knowledge base triggers each detector deterministically.

**Architecture:** Both detectors live in `tools/knowledge/lint.py` so the file stays under the ~400-line split threshold called out in the parent plan. A new `LintConfig` dataclass joins `ProjectConfig` to carry `fuzzy_threshold`. `_default_detectors(config)` grows a single argument so `main()` can wire the threshold through. The Detector `Protocol` is unchanged — both new detectors are plain dataclasses with `code`, `needs_llm`, and `run(nodes, graph, *, llm)`. They store the threshold as a constructor argument; nothing flows through `run`.

**Tech Stack:** Python 3.10+, stdlib (`dataclasses`, `difflib`, `typing.Protocol`, `re`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 3 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PR 1 (`Diagnostic.code` / `Diagnostic.related` / `level="info"`) and PR 2 (`Linter` + renderers + CLI) are already on `main`. PR 2 left `_default_detectors()` returning `[]`; this PR populates it with the first two detectors and verifies the wiring end-to-end.

Real APIs the detectors use (do not reimplement):

- `tools.knowledge.models.Node` — frontmatter `title: str`, `kind: str`, `status: str`, plus `body: str` for fallback statement text when a `## Statement` section is absent.
- `tools.knowledge.models.ADMITTED_STATUSES` (`{"admitted", "formalized", "proved"}`) and `STAGED_STATUSES` (`{"staged", "needs_statement_review", "needs_definition_review", "needs_proof_review"}`) — already exported from `models.py`.
- `tools.knowledge.config.ProjectConfig` — extended in Task 1.
- `tools.knowledge.validator.Diagnostic` — already accepts `code` and `related`.
- `difflib.SequenceMatcher(None, a, b).ratio()` — stdlib fuzzy matcher; quadratic so the all-pairs scan stays well under a second for typical knowledge-base sizes (a few thousand nodes).

The bundled example (`docs/knowledge/`) is the smoke-test target. With the default threshold of `0.92` it must continue to lint cleanly. The fuzzy scan is intentionally conservative; honest false positives are a tuning problem, not a correctness problem.

## File Structure

- **Create**: none.
- **Modify**: `tools/knowledge/config.py` — add `LintConfig`, attach to `ProjectConfig`, extend `load_project_config` to parse it.
- **Modify**: `tools/knowledge/lint.py` — add `_normalize`, `_ratio`, `_statement_text`, `FuzzyTitleDupDetector`, `StagedAdmittedOverlapDetector`; thread the threshold from config through `main → _default_detectors`.
- **Create**: `tests/test_lint_fuzzy.py` — TDD coverage of both detectors with fake-node fixtures.
- **Modify**: `tests/test_config.py` — round-trip case for the new `lint.fuzzy_threshold` field.

`tools/knowledge/lint.py` grows from 182 lines to ~280 lines (well under the 400-line split threshold flagged in the parent plan).

---

### Task 1: `LintConfig` and threshold plumbing

**Files:**
- Modify: `tools/knowledge/config.py`
- Modify: `tests/test_config.py`

#### Step 1.1: Write the first failing test

- [ ] Add this test to `tests/test_config.py` near the other config-loading tests:

```python
def test_load_project_config_reads_lint_fuzzy_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Lint Threshold Test\n"
        "lint:\n  fuzzy_threshold: 0.88\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.88


def test_load_project_config_uses_default_lint_threshold_when_section_missing(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Default Lint Threshold\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.92


def test_load_project_config_rejects_non_numeric_lint_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Bad Lint Threshold\n"
        "lint:\n  fuzzy_threshold: nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fuzzy_threshold"):
        load_project_config(tmp_path)


def test_load_project_config_rejects_lint_threshold_out_of_range(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Out of Range\n"
        "lint:\n  fuzzy_threshold: 1.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="fuzzy_threshold"):
        load_project_config(tmp_path)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py::test_load_project_config_reads_lint_fuzzy_threshold -q`
- [ ] Expected: `AttributeError: 'ProjectConfig' object has no attribute 'lint'` (or equivalent) — the field does not exist yet.

#### Step 1.2: Add the dataclass and parser

- [ ] Insert the dataclass alongside the other `*Config` dataclasses in `tools/knowledge/config.py` (after `SourcesConfig`):

```python
@dataclass(frozen=True)
class LintConfig:
    fuzzy_threshold: float = 0.92
```

- [ ] Add the field to `ProjectConfig` (preserve alphabetical ordering of fields):

```python
@dataclass(frozen=True)
class ProjectConfig:
    site: SiteConfig
    math: MathConfig
    lean: LeanConfig
    graph: GraphDisplayConfig
    topics: tuple[TopicConfig, ...] = field(default_factory=())
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    lint: LintConfig = field(default_factory=LintConfig)
```

- [ ] Add the parser helper near the other `_parse_*_config` helpers:

```python
def _parse_lint_config(raw: Any, *, path: Path) -> LintConfig:
    if raw is None:
        return LintConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config lint must be a mapping: {path}")

    threshold = raw.get("fuzzy_threshold", 0.92)
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise ValueError(
            f"Project config lint.fuzzy_threshold must be a number between 0 and 1: {path}"
        )
    threshold = float(threshold)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            f"Project config lint.fuzzy_threshold must be between 0 and 1, got {threshold}: {path}"
        )

    return LintConfig(fuzzy_threshold=threshold)
```

- [ ] Wire it into `load_project_config`'s return statement:

```python
    return ProjectConfig(
        site=SiteConfig(title=title.strip(), short_title=short_title),
        math=_parse_math_config(raw.get("math"), path=path),
        lean=_parse_lean_config(raw.get("lean"), path=path),
        graph=_parse_graph_config(raw.get("graph"), path=path),
        topics=_parse_topics_config(raw.get("topics"), path=path),
        sources=_parse_sources_config(raw.get("sources"), path=path),
        lint=_parse_lint_config(raw.get("lint"), path=path),
    )
```

- [ ] Update `_fallback_config` so the in-code fallback also exposes the default `LintConfig`:

```python
def _fallback_config(knowledge_root: Path) -> ProjectConfig:
    return ProjectConfig(
        site=SiteConfig(title=_titleize_path_name(knowledge_root.name)),
        math=_default_math_config(),
        lean=_default_lean_config(),
        graph=GraphDisplayConfig(),
        lint=LintConfig(),
    )
```

#### Step 1.3: Run the four new config tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py -q`
- [ ] Expected: every test in `test_config.py` passes, including the four new ones.

#### Step 1.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: all tests pass; baseline grows by 4 (557 → 561).

#### Step 1.5: Commit Task 1

```bash
git add tools/knowledge/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add LintConfig with fuzzy_threshold (default 0.92)

Adds a LintConfig dataclass to ProjectConfig so detectors in PR 3+
can read mdblueprint.yml -> lint.fuzzy_threshold. Parser rejects
non-numeric values and values outside [0, 1]. Defaults to 0.92.
Issue #121, PR 3.
EOF
)"
```

---

### Task 2: Normalization helpers and `FuzzyTitleDupDetector`

**Files:**
- Modify: `tools/knowledge/lint.py`
- Create: `tests/test_lint_fuzzy.py`

#### Step 2.1: Write the first failing tests

- [ ] Create `tests/test_lint_fuzzy.py`:

```python
"""Tests for the fuzzy title / staged-overlap detectors (PR 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import (
    FuzzyTitleDupDetector,
    StagedAdmittedOverlapDetector,
    _normalize,
    _ratio,
)
from tools.knowledge.models import Node


def _node(node_id: str, title: str, *, kind: str = "theorem", status: str = "admitted", body: str = "") -> Node:
    return Node(id=node_id, title=title, kind=kind, status=status, body=body)


class TestNormalize:
    def test_lowercases_and_collapses_whitespace(self):
        assert _normalize("Group  Identity   Is\tUnique") == "group identity is unique"

    def test_strips_leading_and_trailing_punctuation(self):
        assert _normalize("  *Group Identity Is Unique.*  ") == "group identity is unique"

    def test_preserves_internal_punctuation(self):
        # Internal punctuation stays so a sentence-level difference is still distinguishable.
        assert _normalize("If g, h in G, then gh = hg") == "if g, h in g, then gh = hg"


class TestRatio:
    def test_identical_strings_return_one(self):
        assert _ratio("group identity is unique", "group identity is unique") == 1.0

    def test_unrelated_strings_return_low_score(self):
        assert _ratio("group identity is unique", "cauchy schwarz inequality") < 0.5

    def test_near_duplicates_clear_default_threshold(self):
        a = "group identity is unique"
        b = "group identity is unique."
        assert _ratio(_normalize(a), _normalize(b)) >= 0.92


class TestFuzzyTitleDupDetector:
    def test_emits_warning_for_punctuation_variant(self):
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        diags = det.run([a, b], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_FUZZY_DUP"
        # `related` carries the other node's id; the source node_id is the
        # lexicographically smaller of the pair so the diagnostic is stable.
        assert d.node_id == "alg.x"
        assert d.related == ("alg.y",)

    def test_does_not_emit_for_unrelated_titles(self):
        a = _node("alg.group", "Group Identity Is Unique")
        b = _node("ana.cauchy", "Cauchy Schwarz Inequality")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        assert det.run([a, b], graph, llm=None) == []

    def test_ignores_staged_nodes(self):
        # FuzzyTitleDup only considers admitted nodes — staged-vs-admitted
        # overlap is the StagedAdmittedOverlapDetector's job.
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.", status="staged")
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        assert det.run([a, b], graph, llm=None) == []

    def test_threshold_is_respected(self):
        # 0.86 ratio pair should NOT trigger at 0.92 but SHOULD at 0.80.
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity in a group is unique element")
        graph, _ = build_graph([a, b])
        assert FuzzyTitleDupDetector(threshold=0.92).run([a, b], graph, llm=None) == []
        loose = FuzzyTitleDupDetector(threshold=0.50).run([a, b], graph, llm=None)
        assert len(loose) == 1

    def test_uses_statement_when_titles_differ(self):
        # If titles differ but statements are near-identical, still flag.
        a = _node(
            "alg.alpha",
            "Lemma One",
            body="## Statement\nFor every group, the identity element is unique.\n",
        )
        b = _node(
            "alg.beta",
            "Lemma Two",
            body="## Statement\nFor every group, the identity element is unique.\n",
        )
        graph, _ = build_graph([a, b])
        det = FuzzyTitleDupDetector(threshold=0.92)
        diags = det.run([a, b], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].code == "LINT_FUZZY_DUP"

    def test_pair_is_reported_only_once(self):
        # The all-pairs scan must emit a single diagnostic per unordered pair.
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.")
        graph, _ = build_graph([a, b])
        diags = FuzzyTitleDupDetector(threshold=0.92).run([a, b], graph, llm=None)
        ids_seen = [(d.node_id, d.related) for d in diags]
        assert len(ids_seen) == 1
        assert ids_seen[0] == ("alg.x", ("alg.y",))
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_fuzzy.py -q`
- [ ] Expected: `ImportError` for `FuzzyTitleDupDetector` / `_normalize` / `_ratio`.

#### Step 2.2: Implement the helpers and the detector

Add to `tools/knowledge/lint.py` (place after `Linter` and before `render_text`):

```python
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from tools.knowledge.models import ADMITTED_STATUSES, STAGED_STATUSES


_WHITESPACE_RE = re.compile(r"\s+")
_LEADING_TRAILING_PUNCT_RE = re.compile(r"^[\s\W_]+|[\s\W_]+$", flags=re.UNICODE)


def _normalize(text: str) -> str:
    """Lowercase, collapse internal whitespace, strip leading/trailing punctuation.

    Internal punctuation is preserved so semantically distinct sentences with
    similar surface words still stay apart.
    """
    if text is None:
        return ""
    lowered = text.lower()
    stripped = _LEADING_TRAILING_PUNCT_RE.sub("", lowered)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def _ratio(a: str, b: str) -> float:
    """SequenceMatcher ratio over already-normalized strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


_STATEMENT_HEADING_RE = re.compile(r"^##\s+statement\b", flags=re.IGNORECASE | re.MULTILINE)
_HEADING_RE = re.compile(r"^#+\s", flags=re.MULTILINE)


def _statement_text(node: Node) -> str:
    """Return the body text under a `## Statement` section if present, else `""`.

    Used as a secondary similarity signal when titles alone don't trigger.
    """
    body = node.body or ""
    match = _STATEMENT_HEADING_RE.search(body)
    if match is None:
        return ""
    start = match.end()
    # Stop at the next heading of any level.
    next_heading = _HEADING_RE.search(body, pos=start)
    end = next_heading.start() if next_heading else len(body)
    return body[start:end].strip()


@dataclass
class FuzzyTitleDupDetector:
    """Flag admitted node pairs with near-duplicate titles or statements."""

    threshold: float = 0.92
    code: str = "LINT_FUZZY_DUP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        out: list[Diagnostic] = []
        for index, a in enumerate(admitted):
            a_title = _normalize(a.title)
            a_stmt = _normalize(_statement_text(a))
            for b in admitted[index + 1:]:
                b_title = _normalize(b.title)
                score = _ratio(a_title, b_title)
                if score < self.threshold:
                    b_stmt = _normalize(_statement_text(b))
                    if a_stmt and b_stmt:
                        score = max(score, _ratio(a_stmt, b_stmt))
                if score >= self.threshold:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=a.id,
                        message=f"near-duplicate of {b.id!r} (similarity {score:.2f})",
                        file_path=a.file_path,
                        code=self.code,
                        related=(b.id,),
                    ))
        return out
```

The lexicographic ordering of `admitted` plus the `index + 1` inner range guarantees each unordered pair is visited exactly once and `node_id` is always the smaller of the two ids.

#### Step 2.3: Run the fuzzy tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_fuzzy.py -q`
- [ ] Expected: all `_normalize`, `_ratio`, and `FuzzyTitleDupDetector` tests pass.

#### Step 2.4: Run the full suite (no regressions)

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: all tests still pass; baseline grows to 561 + new fuzzy tests.

#### Step 2.5: Commit Task 2

```bash
git add tools/knowledge/lint.py tests/test_lint_fuzzy.py
git commit -m "$(cat <<'EOF'
feat(lint): add FuzzyTitleDupDetector (LINT_FUZZY_DUP)

Adds _normalize/_ratio/_statement_text helpers and a deterministic
SequenceMatcher-backed detector that flags admitted node pairs whose
titles (or, as a secondary signal, the contents of a ## Statement
section) cross the configured similarity threshold. Default
threshold 0.92, configurable via mdblueprint.yml -> lint.fuzzy_threshold.
No new dependencies — pure stdlib difflib. Issue #121, PR 3.
EOF
)"
```

---

### Task 3: `StagedAdmittedOverlapDetector`

**Files:**
- Modify: `tools/knowledge/lint.py`
- Modify: `tests/test_lint_fuzzy.py`

#### Step 3.1: Write the first failing tests

Append to `tests/test_lint_fuzzy.py`:

```python
class TestStagedAdmittedOverlapDetector:
    def test_emits_warning_when_staged_matches_admitted(self):
        admitted = _node("alg.x", "Group Identity Is Unique")
        staged = _node("alg.candidate", "Group Identity Is Unique.", status="staged")
        graph, _ = build_graph([admitted, staged])
        det = StagedAdmittedOverlapDetector(threshold=0.92)
        diags = det.run([admitted, staged], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_STAGED_OVERLAP"
        # The staged node is the source of the diagnostic; `related` holds the
        # admitted node that the candidate appears to duplicate.
        assert d.node_id == "alg.candidate"
        assert d.related == ("alg.x",)

    def test_does_not_emit_for_two_admitted_nodes(self):
        # Two admitted near-duplicates are FuzzyTitleDupDetector's job, not this one.
        a = _node("alg.x", "Group Identity Is Unique")
        b = _node("alg.y", "Group Identity Is Unique.")
        graph, _ = build_graph([a, b])
        assert StagedAdmittedOverlapDetector(threshold=0.92).run([a, b], graph, llm=None) == []

    def test_does_not_emit_for_two_staged_nodes(self):
        a = _node("alg.x", "Group Identity Is Unique", status="staged")
        b = _node("alg.y", "Group Identity Is Unique.", status="staged")
        graph, _ = build_graph([a, b])
        assert StagedAdmittedOverlapDetector(threshold=0.92).run([a, b], graph, llm=None) == []

    def test_ignores_unrelated_staged_candidate(self):
        admitted = _node("alg.x", "Group Identity Is Unique")
        staged = _node("ana.cauchy", "Cauchy Schwarz Inequality", status="needs_statement_review")
        graph, _ = build_graph([admitted, staged])
        assert StagedAdmittedOverlapDetector(threshold=0.92).run([admitted, staged], graph, llm=None) == []

    def test_handles_all_needs_review_statuses(self):
        admitted = _node("alg.x", "Group Identity Is Unique")
        staged_variants = [
            _node("alg.s1", "Group Identity Is Unique.", status="staged"),
            _node("alg.s2", "Group Identity Is Unique.", status="needs_statement_review"),
            _node("alg.s3", "Group Identity Is Unique.", status="needs_definition_review"),
            _node("alg.s4", "Group Identity Is Unique.", status="needs_proof_review"),
        ]
        graph, _ = build_graph([admitted, *staged_variants])
        det = StagedAdmittedOverlapDetector(threshold=0.92)
        diags = det.run([admitted, *staged_variants], graph, llm=None)
        assert {d.node_id for d in diags} == {"alg.s1", "alg.s2", "alg.s3", "alg.s4"}
        assert all(d.related == ("alg.x",) for d in diags)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_fuzzy.py::TestStagedAdmittedOverlapDetector -q`
- [ ] Expected: `ImportError: cannot import name 'StagedAdmittedOverlapDetector'`.

#### Step 3.2: Implement the detector

Append to `tools/knowledge/lint.py` (right after `FuzzyTitleDupDetector`):

```python
@dataclass
class StagedAdmittedOverlapDetector:
    """Flag staged candidate nodes that re-state an already-admitted node."""

    threshold: float = 0.92
    code: str = "LINT_STAGED_OVERLAP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        staged = sorted(
            (n for n in nodes if n.status in STAGED_STATUSES),
            key=lambda n: n.id,
        )
        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        out: list[Diagnostic] = []
        for candidate in staged:
            c_title = _normalize(candidate.title)
            c_stmt = _normalize(_statement_text(candidate))
            for existing in admitted:
                e_title = _normalize(existing.title)
                score = _ratio(c_title, e_title)
                if score < self.threshold:
                    e_stmt = _normalize(_statement_text(existing))
                    if c_stmt and e_stmt:
                        score = max(score, _ratio(c_stmt, e_stmt))
                if score >= self.threshold:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=candidate.id,
                        message=(
                            f"staged candidate appears to overlap with admitted "
                            f"{existing.id!r} (similarity {score:.2f})"
                        ),
                        file_path=candidate.file_path,
                        code=self.code,
                        related=(existing.id,),
                    ))
        return out
```

#### Step 3.3: Run the new test class

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_fuzzy.py::TestStagedAdmittedOverlapDetector -q`
- [ ] Expected: all five `StagedAdmittedOverlapDetector` tests pass.

#### Step 3.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: all tests still pass.

#### Step 3.5: Commit Task 3

```bash
git add tools/knowledge/lint.py tests/test_lint_fuzzy.py
git commit -m "$(cat <<'EOF'
feat(lint): add StagedAdmittedOverlapDetector (LINT_STAGED_OVERLAP)

Uses the same _normalize / _ratio / _statement_text helpers as
FuzzyTitleDupDetector but restricts the pair set to
(staged x admitted). Surfaces candidate nodes that silently restate
already-admitted material before reviewers have to read both.
Issue #121, PR 3.
EOF
)"
```

---

### Task 4: Wire detectors into `_default_detectors()` and the CLI

**Files:**
- Modify: `tools/knowledge/lint.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 4.1: Write the first failing test

Append a test class to `tests/test_lint_orchestrator.py`:

```python
class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            StagedAdmittedOverlapDetector,
            _default_detectors,
        )

        detectors = _default_detectors(LintConfig(fuzzy_threshold=0.77))
        codes = {d.code for d in detectors}
        assert "LINT_FUZZY_DUP" in codes
        assert "LINT_STAGED_OVERLAP" in codes

        fuzzy = next(d for d in detectors if isinstance(d, FuzzyTitleDupDetector))
        overlap = next(d for d in detectors if isinstance(d, StagedAdmittedOverlapDetector))
        assert fuzzy.threshold == 0.77
        assert overlap.threshold == 0.77

    def test_main_runs_default_detectors_against_bundled_example(self, capsys):
        from tools.knowledge.lint import main

        exit_code = main(["docs/knowledge"])
        captured = capsys.readouterr()
        assert exit_code == 0
        # Default detectors must be quiet on the bundled example at the default
        # threshold. Any change to the example or threshold that surfaces a real
        # finding here should be addressed in the example/threshold, not the test.
        assert "No lint findings" in captured.out
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring -q`
- [ ] Expected: `TypeError: _default_detectors() takes 0 positional arguments but 1 was given` (the existing signature is `() -> list[Detector]`).

#### Step 4.2: Update `_default_detectors` to take a config

Edit `tools/knowledge/lint.py`:

```python
def _default_detectors(config: "LintConfig | None" = None) -> list[Detector]:
    """Return the built-in detector list. PR 3 introduces the first two."""
    from tools.knowledge.config import LintConfig as _LintConfig
    cfg = config if config is not None else _LintConfig()
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
    ]
```

Note the deferred import — keeping `tools.knowledge.config` out of the module-level imports avoids a circular dependency since `config.py` does not currently import from `lint.py` but may in future iterations. If the import order is verified clean (which it is in this PR), promoting it to a module-level import is fine. The local import is the conservative default.

#### Step 4.3: Thread the config through `main`

Update `main()` in `tools/knowledge/lint.py`:

```python
def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    from tools.knowledge.config import load_project_config

    config = load_project_config(args.knowledge_root)
    llm: LlmRunner | None = None
    if args.llm:
        llm = _make_claude_cli_runner(model=args.model)
    linter = Linter(detectors=_default_detectors(config.lint), llm=llm)
    diags = linter.run(args.knowledge_root)
    output = render_json(diags) if args.json else render_text(diags)
    print(output)
    if any(d.level == "error" for d in diags):
        return 1
    if args.strict_warnings and any(d.level == "warning" for d in diags):
        return 1
    return 0
```

#### Step 4.4: Update existing orchestrator tests that assumed empty defaults

PR 2's `tests/test_lint_orchestrator.py` includes assertions that rely on `_default_detectors()` being callable with no arguments and returning `[]`. Audit those:

- [ ] Grep: `grep -n "_default_detectors" tests/test_lint_orchestrator.py`
- [ ] For each call site that passes no argument and asserts `== []`, update to either pass `LintConfig()` explicitly **or** assert on the new shape (two built-in detectors). Prefer the latter — the empty-default contract was always a PR-2 placeholder.

Example transformation:

```python
# Before (PR 2 placeholder):
assert _default_detectors() == []

# After (PR 3):
from tools.knowledge.config import LintConfig
detectors = _default_detectors(LintConfig())
assert {d.code for d in detectors} == {"LINT_FUZZY_DUP", "LINT_STAGED_OVERLAP"}
```

If a test was checking that "no detectors fire on the empty example", it should keep working unchanged because the real detectors don't fire either; the assertion should reference `diags` (`== []` or `all(d.code is None ...)`), not the size of `_default_detectors()`.

#### Step 4.5: Run the orchestrator tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py -q`
- [ ] Expected: all tests pass, including the two new wiring tests.

#### Step 4.6: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: every test passes.

#### Step 4.7: Re-install so the entry point picks up the new wiring

- [ ] Run: `uv sync --extra dev 2>&1 | tail -5`
- [ ] Expected: brief resolved/installed summary, no errors.

#### Step 4.8: Smoke against the bundled example

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: `✅ No lint findings.` and exit 0.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --json`
- [ ] Expected: `[]` and exit 0.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --strict-warnings`
- [ ] Expected: exit 0 (no warnings at the default 0.92 threshold).

If any of these surface findings, that's either a real issue in the bundled example or a threshold that needs raising. Investigate before continuing — Definition of Done requires the bundled example to lint cleanly at default settings.

#### Step 4.9: Confirm `mdblueprint-check` output unchanged

- [ ] Capture before and after:

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output. PR 3 must not change `check`'s observable behavior.

#### Step 4.10: Commit Task 4

```bash
git add tools/knowledge/lint.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): wire FuzzyTitleDup + StagedAdmittedOverlap into default detectors

_default_detectors(config) now returns the two PR 3 detectors with
their threshold taken from LintConfig. main() loads the project
config and passes the lint section through. The bundled example
continues to lint cleanly at the default 0.92 threshold.
Issue #121, PR 3.
EOF
)"
```

---

## Definition of Done

- [ ] `tools/knowledge/config.py` exports a `LintConfig` dataclass attached to `ProjectConfig`; `load_project_config` parses `lint.fuzzy_threshold` and rejects non-numeric / out-of-range values.
- [ ] `tools/knowledge/lint.py` defines `_normalize`, `_ratio`, `_statement_text`, `FuzzyTitleDupDetector`, `StagedAdmittedOverlapDetector`; both detectors expose `code`, `needs_llm = False`, and `run(...) -> list[Diagnostic]`.
- [ ] `_default_detectors(config)` returns `[FuzzyTitleDupDetector(threshold=config.fuzzy_threshold), StagedAdmittedOverlapDetector(threshold=config.fuzzy_threshold)]`.
- [ ] `main()` loads `ProjectConfig` and threads `config.lint` through.
- [ ] `tests/test_lint_fuzzy.py` covers normalization, ratio, both detector positive cases, and at least one negative case per detector.
- [ ] `tests/test_lint_orchestrator.py` covers the `_default_detectors(config)` wiring and the end-to-end smoke against `docs/knowledge`.
- [ ] `tests/test_config.py` covers the new `lint` section (default, custom, rejection paths).
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0 with no findings at the default 0.92 threshold.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` output is byte-identical before and after the PR.
- [ ] Four commits on `feat/lint-pr3-dup-and-overlap` (config, fuzzy detector, overlap detector, wiring), no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint.py` is under 400 lines (the split threshold flagged in the parent plan).

## Hand-off to PR 4

PR 4 (redundant deps + orphans, codes `LINT_REDUNDANT_DEP` and `LINT_ORPHAN`) lives entirely in graph-shape analysis — no string normalization, no LLM. It plugs detectors into the same `_default_detectors(config)` slot via additional positional list entries; no further infrastructure changes are required. If `lint.py` is approaching ~400 lines after PR 4, that's the moment to split into `tools/knowledge/lint/__init__.py` + `tools/knowledge/lint/_detectors/*.py` as called out in the parent plan's Risk Notes.
