# Blueprint Lint PR 8 — Promote-via-Plan Detector + Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the blueprint-lint sequence with two deliverables.

1. The `PlanCompletedButStatusNotPromotedDetector` (code `LINT_PLAN_PROMOTE`) called for by [#127](https://github.com/gametheoryinlean/mdblueprint/issues/127): emit one diagnostic per theorem-like node whose attached proof plan supplies a complete Lean proof but whose own `status` has not yet been promoted to `proved` (and where the `proved_via_plan` marker is also absent, since either signal carries the author's intent). The detector is deterministic, doesn't need an LLM, and reuses `tools.knowledge.blueprint_view.plan_provides_proof` so the lint and view layer share one truth.
2. Documentation: a new `docs/lint.md` with one section per rule code (what it checks, an example trigger, how to fix), an `AGENTS.md` Common Task Map row for `mdblueprint-lint`, and a short README link.

**Architecture:** The detector lives in `tools/knowledge/lint/_detectors.py` (deterministic, no LLM). It accepts `severity: str = "info"` so projects can dial the warning level via `mdblueprint.yml → lint.plan_promote_severity` if the default `info` proves too quiet. `_default_detectors(config, ...)` appends the new detector; the parent plan does not require new CLI flags.

`docs/lint.md` is the canonical reference for every `LINT_*` code; each section names the code, the trigger condition (in plain English), an example, and the recommended fix. `AGENTS.md` gains one row pointing at the lint module and a minimum verification recipe.

**Tech Stack:** Python 3.10+, stdlib (`dataclasses`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 8 row).

**Tracking issues:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121), [#127](https://github.com/gametheoryinlean/mdblueprint/issues/127).

---

## Context

PRs 1-7 plus two refactors landed. After PR 7, `tools/knowledge/lint/` contains:

```
__init__.py    public re-exports
_core.py       Detector protocol, Linter, renderers, CLI, _default_detectors, main
_cache.py      _LintCache, _BudgetTracker, _content_hash
_detectors.py  deterministic detectors (~373 lines)
_llm.py        SemanticDup + LeanAlignment detectors (~346 lines)
```

Rule codes already shipped:
- `LINT_FUZZY_DUP`, `LINT_STAGED_OVERLAP` (PR 3)
- `LINT_REDUNDANT_DEP`, `LINT_ORPHAN` (PR 4)
- `LINT_LEAN_KIND` (PR 5)
- `LINT_SEMANTIC_DUP` (PR 6)
- `LINT_LEAN_ALIGN` (PR 7)

PR 8 adds `LINT_PLAN_PROMOTE` and produces the public docs covering all eight.

The detector reuses logic already in `tools.knowledge.blueprint_view`:
- `plan_provides_proof(plan_id, g)` — returns True iff the plan's `status` is `formalized`/`proved` AND every transitive ancestor of the plan is also formalized/proved or a definition-kind node. Already covered by `tests/test_blueprint_view.py::test_plan_provides_proof_predicate`.
- `g.proof_plans_by_target` — the inverted attachment map from `tools.knowledge.graph.build_graph`.

`tests/test_promote_via_plan.py` proves the predicate's behavior end-to-end; the new lint detector just iterates targets and asks the predicate.

Authors who *do* want auto-write to YAML run `tools/knowledge/promote_via_plan.py` (shipped in #128). The detector and the CLI both rely on the same predicate, so they will always agree about which theorems are candidates.

## File Structure

- **Create**: `docs/lint.md` — one section per `LINT_*` code, plus a top-level overview and an "Adding a detector" pointer to the parent plan.
- **Modify**: `tools/knowledge/lint/_detectors.py` — append `PlanCompletedButStatusNotPromotedDetector` (referred to from here on as `PlanPromoteDetector` for brevity, matching the export name in `__init__.py`).
- **Modify**: `tools/knowledge/lint/__init__.py` — re-export `PlanPromoteDetector`.
- **Modify**: `tools/knowledge/lint/_core.py` — append to `_default_detectors`.
- **Modify**: `tools/knowledge/config.py` — add `LintConfig.plan_promote_severity: str = "info"` with validation against `{"info", "warning"}`.
- **Create**: `tests/test_lint_plan_promote.py` — deterministic-detector coverage.
- **Modify**: `tests/test_lint_orchestrator.py` — `TestDefaultDetectorsWiring` adds `LINT_PLAN_PROMOTE`.
- **Modify**: `tests/test_config.py` — round-trip the new severity field.
- **Modify**: `AGENTS.md` — Common Task Map row for `mdblueprint-lint`.
- **Modify**: `README.md` — one-line link to `docs/lint.md` if there is a checks/QA section already present; otherwise skip with a brief note in the final report.

After PR 8, `tools/knowledge/lint/_detectors.py` is projected at ~430 lines (PR 7 left it at 373; the new detector + helpers add ~55). Still under the 500-line per-file cap with margin.

---

### Task 1: `LintConfig.plan_promote_severity`

**Files:**
- Modify: `tools/knowledge/config.py`
- Modify: `tests/test_config.py`

#### Step 1.1: Write the first failing tests

Append to `tests/test_config.py`:

```python
def test_load_project_config_reads_plan_promote_severity(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Plan Promote Severity Test\n"
        "lint:\n  plan_promote_severity: warning\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.plan_promote_severity == "warning"


def test_load_project_config_uses_default_plan_promote_severity(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Default Plan Promote Severity\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.plan_promote_severity == "info"


def test_load_project_config_rejects_invalid_plan_promote_severity(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Invalid Plan Promote Severity\n"
        "lint:\n  plan_promote_severity: shout\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="plan_promote_severity"):
        load_project_config(tmp_path)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py::test_load_project_config_reads_plan_promote_severity -q`
- [ ] Expected: `AttributeError` on the missing field.

#### Step 1.2: Extend the dataclass and parser

In `tools/knowledge/config.py`:

```python
@dataclass(frozen=True)
class LintConfig:
    fuzzy_threshold: float = 0.92
    semantic_candidate_threshold: float = 0.75
    plan_promote_severity: str = "info"
```

Extend `_parse_lint_config`:

```python
def _parse_lint_config(raw: Any, *, path: Path) -> LintConfig:
    if raw is None:
        return LintConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"Project config lint must be a mapping: {path}")

    fuzzy_threshold = _parse_unit_interval(
        raw.get("fuzzy_threshold", 0.92),
        path=path,
        field="fuzzy_threshold",
    )
    semantic_candidate_threshold = _parse_unit_interval(
        raw.get("semantic_candidate_threshold", 0.75),
        path=path,
        field="semantic_candidate_threshold",
    )
    severity = raw.get("plan_promote_severity", "info")
    if severity not in {"info", "warning"}:
        raise ValueError(
            f"Project config lint.plan_promote_severity must be 'info' or 'warning', "
            f"got {severity!r}: {path}"
        )

    return LintConfig(
        fuzzy_threshold=fuzzy_threshold,
        semantic_candidate_threshold=semantic_candidate_threshold,
        plan_promote_severity=severity,
    )
```

#### Step 1.3: Run config tests + full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py -q`
- [ ] Expected: all tests pass, including the three new ones.
- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 1.4: Commit Task 1

```bash
git add tools/knowledge/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add LintConfig.plan_promote_severity (default 'info')

Lets projects dial the upcoming PlanPromoteDetector between info
(default — non-blocking nudge) and warning (escalates to a real
finding promoted by --strict-warnings). Validation rejects any
value other than 'info' or 'warning'. Issue #121, PR 8.
EOF
)"
```

---

### Task 2: `PlanPromoteDetector`

**Files:**
- Modify: `tools/knowledge/lint/_detectors.py`
- Modify: `tools/knowledge/lint/__init__.py`
- Create: `tests/test_lint_plan_promote.py`

#### Step 2.1: Write the first failing tests

- [ ] Create `tests/test_lint_plan_promote.py`:

```python
"""Tests for PlanPromoteDetector (PR 8 / closes #127)."""
from __future__ import annotations

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import PlanPromoteDetector
from tools.knowledge.models import LeanRef, Node


def _node(node_id: str, *, kind: str = "theorem", status: str = "formalized",
          uses: list[str] | None = None, proved_via_plan: str | None = None,
          lean: LeanRef | None = None) -> Node:
    kwargs: dict = {
        "id": node_id,
        "title": node_id,
        "kind": kind,
        "status": status,
        "uses": list(uses or []),
    }
    if proved_via_plan is not None:
        kwargs["proved_via_plan"] = proved_via_plan
    if lean is not None:
        kwargs["lean"] = lean
    return Node(**kwargs)


class TestEmitsOnce:
    def test_theorem_with_ready_plan_and_unpromoted_status_is_flagged(self):
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])

        det = PlanPromoteDetector()
        diags = det.run([base, plan, thm], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"  # default severity
        assert d.code == "LINT_PLAN_PROMOTE"
        assert d.node_id == "topic.thm"
        # related names the plan that supplies the proof.
        assert d.related == ("topic.thm.plan.direct",)
        # Message mentions both endpoints and the canonical fix.
        assert "topic.thm" in d.message
        assert "topic.thm.plan.direct" in d.message
        assert "promote" in d.message.lower() or "proved_via_plan" in d.message.lower()


class TestSeverity:
    def test_severity_warning_promotes_diagnostic_level(self):
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])

        det = PlanPromoteDetector(severity="warning")
        diags = det.run([base, plan, thm], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "warning"

    def test_severity_other_values_rejected_at_construction(self):
        with pytest.raises(ValueError):
            PlanPromoteDetector(severity="shout")


class TestSilentPaths:
    def test_already_proved_theorem_is_silent(self):
        # status: proved means the author has already done the promotion;
        # the detector should not nag.
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node(
            "topic.thm", kind="theorem", status="proved",
            proved_via_plan="topic.thm.plan.direct",
            lean=LeanRef(modules=["Lib.Mod"], declarations=["Lib.thm"]),
        )
        graph, _ = build_graph([base, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, plan, thm], graph, llm=None) == []

    def test_plan_not_yet_ready_is_silent(self):
        # The plan exists but is staged — nothing to promote yet.
        base = _node("topic.base", kind="definition", status="formalized")
        plan = Node(
            id="topic.thm.plan.draft",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, plan, thm], graph, llm=None) == []

    def test_plan_ancestor_not_ready_is_silent(self):
        # Plan itself is formalized, but it transitively depends on an
        # admitted lemma whose own proof is not in Lean — plan does not
        # actually supply a complete proof.
        base = _node("topic.base", kind="definition", status="formalized")
        intermediate = _node(
            "topic.intermediate", kind="lemma", status="admitted",
            uses=["topic.base"],
        )
        plan = Node(
            id="topic.thm.plan.via_intermediate",
            title="Plan",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.intermediate"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, intermediate, plan, thm])
        det = PlanPromoteDetector()
        assert det.run([base, intermediate, plan, thm], graph, llm=None) == []

    def test_theorem_with_no_attached_plan_is_silent(self):
        # No plans at all — the detector has nothing to nudge about.
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([thm])
        det = PlanPromoteDetector()
        assert det.run([thm], graph, llm=None) == []

    def test_non_theorem_kind_is_skipped(self):
        # Only theorem-like nodes can carry proved_via_plan markers.
        defn = _node("topic.x", kind="definition", status="formalized")
        graph, _ = build_graph([defn])
        det = PlanPromoteDetector()
        assert det.run([defn], graph, llm=None) == []


class TestMultiplePlans:
    def test_prefers_selected_plan_in_related(self):
        # Two qualifying plans; the diagnostic should name the selected one
        # so authors who run `promote_via_plan` get a consistent answer.
        base = _node("topic.base", kind="definition", status="formalized")
        candidate = Node(
            id="topic.thm.plan.alpha",
            title="Alpha",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="candidate",
            uses=["topic.base"],
        )
        selected = Node(
            id="topic.thm.plan.beta",
            title="Beta",
            kind="proof-plan",
            status="formalized",
            target="topic.thm",
            plan_status="selected",
            uses=["topic.base"],
        )
        thm = _node("topic.thm", kind="theorem", status="formalized")
        graph, _ = build_graph([base, candidate, selected, thm])
        det = PlanPromoteDetector()
        diags = det.run([base, candidate, selected, thm], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].related == ("topic.thm.plan.beta",)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_plan_promote.py -q`
- [ ] Expected: `ImportError: cannot import name 'PlanPromoteDetector'`.

#### Step 2.2: Implement the detector

Append to `tools/knowledge/lint/_detectors.py`:

```python
from tools.knowledge.blueprint_view import plan_provides_proof


_PLAN_PROMOTE_VALID_SEVERITIES = frozenset({"info", "warning"})
_PLAN_PROMOTE_TARGET_KINDS = frozenset({"lemma", "proposition", "theorem", "external-theorem"})


def _canonical_plan_for_target(target_id: str, graph: KnowledgeGraph) -> str | None:
    """Mirror tools.knowledge.promote_via_plan._canonical_plan."""
    candidates = [
        plan_id
        for plan_id in graph.proof_plans_by_target.get(target_id, [])
        if plan_provides_proof(plan_id, graph)
    ]
    if not candidates:
        return None
    selected = sorted(
        plan_id for plan_id in candidates
        if graph.nodes[plan_id].plan_status == "selected"
    )
    if selected:
        return selected[0]
    return sorted(candidates)[0]


@dataclass
class PlanPromoteDetector:
    """Nudge authors to run `promote_via_plan` (or hand-write status=proved)
    when an attached plan already supplies a complete Lean proof."""

    severity: str = "info"
    code: str = "LINT_PLAN_PROMOTE"
    needs_llm: bool = False

    def __post_init__(self) -> None:
        if self.severity not in _PLAN_PROMOTE_VALID_SEVERITIES:
            raise ValueError(
                f"PlanPromoteDetector severity must be 'info' or 'warning', "
                f"got {self.severity!r}"
            )

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            if node.kind not in _PLAN_PROMOTE_TARGET_KINDS:
                continue
            if node.status == "proved":
                continue
            plan_id = _canonical_plan_for_target(node.id, graph)
            if plan_id is None:
                continue
            out.append(Diagnostic(
                level=self.severity,
                node_id=node.id,
                message=(
                    f"plan {plan_id!r} provides a complete Lean proof for "
                    f"{node.id!r} (status={node.status!r}). Consider running "
                    f"`uv run python -m tools.knowledge.promote_via_plan` "
                    f"or setting `status: proved` + "
                    f"`proved_via_plan: {plan_id}` manually."
                ),
                file_path=node.file_path,
                code=self.code,
                related=(plan_id,),
            ))
        return out
```

#### Step 2.3: Re-export

- [ ] Add `PlanPromoteDetector` to `tools/knowledge/lint/__init__.py` (re-export from `_detectors`) and `__all__`.

#### Step 2.4: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_plan_promote.py -q`
- [ ] Expected: every test passes.

#### Step 2.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green; ~660 passing (645 baseline + ~9 plan_promote + ~3 config = ~657, close enough to ~660).

#### Step 2.6: Commit Task 2

```bash
git add tools/knowledge/lint/_detectors.py tools/knowledge/lint/__init__.py tests/test_lint_plan_promote.py
git commit -m "$(cat <<'EOF'
feat(lint): add PlanPromoteDetector (LINT_PLAN_PROMOTE) — closes #127

For every theorem-like node whose status is not yet 'proved' but
which has an attached proof plan satisfying
blueprint_view.plan_provides_proof (plan status formalized/proved
plus every transitive ancestor formalized/proved/definition),
surface one diagnostic with the canonical plan id in `related`.
The selected plan wins canonicalisation; ties break by sorted
plan id, mirroring tools.knowledge.promote_via_plan.

Default severity is info — a soft nudge so author-controlled
status fields are never silently overridden. Set
`lint.plan_promote_severity: warning` in mdblueprint.yml to make
it strict.

Pairs with the promote_via_plan CLI shipped in #128: both share
the plan_provides_proof predicate, so they always agree on which
theorems are candidates. Issue #121, closes #127.
EOF
)"
```

---

### Task 3: Wire `PlanPromoteDetector` into `_default_detectors`

**Files:**
- Modify: `tools/knowledge/lint/_core.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 3.1: Update `TestDefaultDetectorsWiring`

In `tests/test_lint_orchestrator.py`, add `LINT_PLAN_PROMOTE` to the expected code set and assert severity threading:

```python
class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            LeanAlignmentLlmDetector,
            LeanRefKindDetector,
            PlanPromoteDetector,
            SemanticDupDetector,
            StagedAdmittedOverlapDetector,
            _default_detectors,
        )

        detectors = _default_detectors(
            LintConfig(
                fuzzy_threshold=0.77,
                semantic_candidate_threshold=0.6,
                plan_promote_severity="warning",
            ),
        )
        codes = {d.code for d in detectors}
        assert codes >= {
            "LINT_FUZZY_DUP",
            "LINT_STAGED_OVERLAP",
            "LINT_REDUNDANT_DEP",
            "LINT_ORPHAN",
            "LINT_LEAN_KIND",
            "LINT_SEMANTIC_DUP",
            "LINT_LEAN_ALIGN",
            "LINT_PLAN_PROMOTE",
        }

        # ... existing threshold assertions stay ...

        promote = next(d for d in detectors if isinstance(d, PlanPromoteDetector))
        assert promote.severity == "warning"
```

#### Step 3.2: Update `_default_detectors`

In `tools/knowledge/lint/_core.py`:

```python
def _default_detectors(
    config: "LintConfig | None" = None,
    *,
    lean_indexes: "dict[str, LeanIndex] | None" = None,
    cache: "_LintCache | None" = None,
    budget: "_BudgetTracker | None" = None,
) -> list[Detector]:
    from tools.knowledge.config import LintConfig as _LintConfig
    from tools.knowledge.lint._cache import _BudgetTracker as _BT, _LintCache as _LC
    from tools.knowledge.lint._llm import LeanAlignmentLlmDetector, SemanticDupDetector
    cfg = config if config is not None else _LintConfig()
    cache = cache if cache is not None else _LC(cache_dir=None)
    budget = budget if budget is not None else _BT(budget=None)
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
        LeanRefKindDetector(indexes=lean_indexes),
        PlanPromoteDetector(severity=cfg.plan_promote_severity),
        SemanticDupDetector(
            cache=cache,
            budget=budget,
            candidate_threshold=cfg.semantic_candidate_threshold,
        ),
        LeanAlignmentLlmDetector(
            cache=cache,
            budget=budget,
            indexes=lean_indexes,
        ),
    ]
```

#### Step 3.3: Smoke

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: PR 7 baseline (2 LINT_REDUNDANT_DEP + 1 LINT_LEAN_KIND info) **plus any LINT_PLAN_PROMOTE findings produced by the bundled example**. If new info findings appear (e.g. a theorem whose plan is fully formalized but whose status is still formalized), they are real and should be reported in the final report — do **NOT** modify the bundled example to silence them.

  Exit code remains 0 (info-level only, by default).

#### Step 3.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 3.5: `mdblueprint-check` byte-identical

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: empty diff.

#### Step 3.6: Commit Task 3

```bash
git add tools/knowledge/lint/_core.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): include PlanPromoteDetector in _default_detectors

Threads cfg.plan_promote_severity through so projects can promote
the detector to warning via mdblueprint.yml. Default severity is
info — no behaviour change on the bundled example except possibly
new info findings, which are real and should be acted on rather
than silenced. Issue #121, closes #127.
EOF
)"
```

---

### Task 4: `docs/lint.md` reference

**Files:**
- Create: `docs/lint.md`

#### Step 4.1: Write `docs/lint.md`

- [ ] Create `docs/lint.md`:

```markdown
# `mdblueprint-lint`

`mdblueprint-lint` is the project's structural and semantic linter. It
extends `mdblueprint-check` (which enforces the publish gate) with rule-
coded findings that surface duplication, structural smells, Lean-link
mismatches, and editorial workflow gaps.

## Running it

```bash
uv run mdblueprint-lint docs/knowledge
uv run mdblueprint-lint docs/knowledge --json
uv run mdblueprint-lint docs/knowledge --strict-warnings
```

`--strict-warnings` makes warning-level findings exit non-zero. Info-level
findings never affect the exit code by themselves.

LLM-backed detectors are off by default:

```bash
uv run mdblueprint-lint docs/knowledge --llm --llm-budget 50
```

`--llm-budget` caps total LLM calls per run; cached judgements still count
toward dedupe but not toward the budget. `--cache-dir` defaults to
`.mdblueprint/lint-cache`; `--no-cache` disables persistence (intra-run
dedupe still works).

## Configuration (`mdblueprint.yml`)

```yaml
lint:
  fuzzy_threshold: 0.92            # LINT_FUZZY_DUP / LINT_STAGED_OVERLAP
  semantic_candidate_threshold: 0.75  # LINT_SEMANTIC_DUP candidate selection
  plan_promote_severity: info      # LINT_PLAN_PROMOTE level: info | warning
```

## Rule reference

### `LINT_FUZZY_DUP` — Near-duplicate admitted nodes

**Trigger.** Two admitted nodes whose normalized titles (or, as a
secondary signal, the contents of their `## Statement` sections) reach
similarity ≥ `lint.fuzzy_threshold`.

**Level.** `warning`. `related` carries the other node id.

**Example.**

```
alg.x  title: "Group Identity Is Unique"
alg.y  title: "Group Identity Is Unique."
```

**How to fix.** Pick the canonical node; delete the duplicate (or mark it
`status: deprecated` and add a `previous_ids:` redirect if the URL needs
to live on).

### `LINT_STAGED_OVERLAP` — Staged candidate restates an admitted node

**Trigger.** A staged node whose normalized title/statement is similar
(≥ `lint.fuzzy_threshold`) to an already-admitted node.

**Level.** `warning`. `related` carries the admitted node id.

**How to fix.** Either retire the staged candidate (it adds nothing) or
rewrite it to be genuinely distinct before the next admission round.

### `LINT_REDUNDANT_DEP` — Direct `uses` edge implied by a transitive path

**Trigger.** Node `T` has `uses: [..., P, ...]` and reaches `P` through
another path of length ≥ 2 in the dependency graph.

**Level.** `info`. `related` carries the redundant prerequisite id.

**Example.** `T.uses = [A, B]`, `B.uses = [A]` ⇒ `T → A` is redundant.

**How to fix.** Remove the redundant id from the dependent node's `uses:`.

### `LINT_ORPHAN` — Node with no incoming or outgoing dependencies

**Trigger.** A node with `in_degree == 0` and `out_degree == 0` in the
dependency graph, **and** no proof-plan attachment in either direction.

**Level.** `info`.

**How to fix.** Either wire the node into the graph by adding `uses:` /
attaching a plan, or remove it. There is no exception list this release;
genuine standalone topic anchors will surface here.

### `LINT_LEAN_KIND` — Lean declaration kind contradicts mdblueprint kind

**Trigger.** Node `kind=definition`/`concept` ties to a Lean `theorem`
or `lemma`, or node `kind=theorem`/`lemma`/`proposition`/`external-theorem`
ties to a Lean `def`/`abbrev`/`structure`/`class`/`inductive`/`instance`.

**Level.** `warning`. `related` carries the Lean declaration name.

**How to fix.** Either the node's `kind:` is wrong or the wrong Lean
entity got wired in. Fix whichever is wrong.

**Skip behaviour.** When no Lean repository is configured (or every
configured repo fails to index), the detector emits one
`info` "lean index not available; skipping LINT_LEAN_KIND" instead of
running, so the rest of the lint pass stays useful.

### `LINT_PLAN_PROMOTE` — Theorem has a completed plan but is not `proved`

**Trigger.** Theorem-like node `T` with `status != "proved"` and at least
one attached plan `P` satisfying:
- `P.status` is `formalized` or `proved`
- every transitive ancestor of `P` is itself `formalized`/`proved` or a
  definition-kind node.

**Level.** `info` by default. Set `lint.plan_promote_severity: warning`
in `mdblueprint.yml` to make it strict.

**How to fix.** Run `uv run python -m tools.knowledge.promote_via_plan
docs/knowledge` to auto-write `status: proved` and the
`proved_via_plan: <plan_id>` marker, or do the same by hand. The
detector picks the same canonical plan as the CLI (selected plan wins;
ties break by sorted plan id), so the two stay in agreement.

### `LINT_SEMANTIC_DUP` — LLM-judged semantic duplicate (`--llm` only)

**Trigger.** Admitted pair whose fuzzy ratio reaches
`lint.semantic_candidate_threshold` (default `0.75`, below the
`fuzzy_threshold` so PR 3's deterministic detector wouldn't have
flagged it). The detector asks the configured LLM whether the two
nodes state the same theorem; `same: true` ⇒ warning.

**Level.** `warning`. `related` carries the other node id.

**Caching.** Decisions are content-hashed into `.mdblueprint/lint-cache/`
(or wherever `--cache-dir` points). Cache survives across runs and is
invalidated when the prompt version constant or any node's
title/statement changes.

**How to fix.** Same as `LINT_FUZZY_DUP`: pick a canonical node and
retire or redirect the duplicate.

### `LINT_LEAN_ALIGN` — Statement does not align with Lean declaration (`--llm` only)

**Trigger.** A theorem-like or definition-like node carrying a Lean
declaration that resolves cleanly through the index, with the LLM
judging that the Markdown statement and Lean signature describe
different things (`aligned: false`).

**Level.** `warning`. `related` carries the Lean declaration name.

**How to fix.** Either the Markdown statement is sloppy and needs
tightening, or the wrong Lean entity was wired in. Fix whichever is
wrong; consider also raising the issue in the corresponding source
review if the Lean side is right and the Markdown is informal.

## How LLM-backed detectors degrade

Every LLM-backed detector:

- Stays silent (returns no diagnostics) when `--llm` is unset.
- Emits one info diagnostic and returns early when its required
  resources are missing (`LINT_LEAN_KIND` / `LINT_LEAN_ALIGN` when no
  index is configured).
- Emits one info diagnostic and stops when `--llm-budget` is reached;
  unprocessed candidates are silently skipped (re-run after raising the
  budget to pick them up).
- Falls back to one info diagnostic per pair when the model response
  fails to parse; the cache stores the failure so the model is not
  re-asked until prompt-version changes or the cache is cleared.

## Adding a new detector

See `tools/knowledge/lint/_detectors.py` for the deterministic-detector
template and `tools/knowledge/lint/_llm.py` for the LLM-backed template.
The `Detector` protocol in `tools/knowledge/lint/_core.py` is the source
of truth; everything else plugs in via `_default_detectors(config, ...)`.
```

- [ ] Verify the file renders without obvious markdown errors (open it in any markdown previewer, or just scan for stray backticks).

#### Step 4.2: Commit Task 4

```bash
git add docs/lint.md
git commit -m "$(cat <<'EOF'
docs(lint): publish docs/lint.md with one section per LINT_* code

Authoritative reference for mdblueprint-lint: CLI invocation, the
LLM gating flags, mdblueprint.yml configuration, and per-rule
trigger/level/fix guidance for all eight codes (LINT_FUZZY_DUP,
LINT_STAGED_OVERLAP, LINT_REDUNDANT_DEP, LINT_ORPHAN,
LINT_LEAN_KIND, LINT_PLAN_PROMOTE, LINT_SEMANTIC_DUP,
LINT_LEAN_ALIGN). Issue #121, PR 8.
EOF
)"
```

---

### Task 5: `AGENTS.md` row + optional README link

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` (skip if no QA/checks section exists)

#### Step 5.1: Append to `AGENTS.md` Common Task Map

Add a row to the existing Common Task Map table (alphabetical insertion is fine; or after the `promote_via_plan` row added in #128):

```markdown
| Run blueprint-lint over a knowledge base | `tools/knowledge/lint/`, `docs/lint.md` | `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py tests/test_lint_fuzzy.py tests/test_lint_structure.py tests/test_lint_lean_kind.py tests/test_lint_cache.py tests/test_lint_llm_semantic.py tests/test_lint_llm_lean_align.py tests/test_lint_plan_promote.py -q`, then `uv run mdblueprint-lint docs/knowledge` (add `--llm` to enable LINT_SEMANTIC_DUP / LINT_LEAN_ALIGN) |
```

#### Step 5.2: Optional README link

- [ ] Open `README.md` and look for an existing "Checks" / "QA" / "Tools" section.
- [ ] If one exists: add a one-line bullet `- [Lint guide](docs/lint.md) — rule reference and CLI flags for \`mdblueprint-lint\`.`
- [ ] If no obvious section exists: skip this step. Note "README has no checks section; skipped per plan" in the final report.

#### Step 5.3: Verify docs tests still pass

- [ ] Run: `uv run --extra dev python -m pytest tests/test_graph_navigation_docs.py tests/test_agent_docs.py -q`
- [ ] Expected: all pass.

#### Step 5.4: Run the full suite once more

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 5.5: Commit Task 5

```bash
git add AGENTS.md README.md
git commit -m "$(cat <<'EOF'
docs(lint): add mdblueprint-lint row to AGENTS.md Common Task Map

Points contributors at tools/knowledge/lint/ and docs/lint.md and
gives a minimum verification recipe that runs every lint-suite
test file plus the bundled-example smoke. Optional README link to
docs/lint.md added if a checks/QA section already exists. Issue
#121, PR 8.
EOF
)"
```

(If README was not modified, the commit covers only AGENTS.md.)

---

## Definition of Done

- [ ] `LintConfig.plan_promote_severity` accepts `"info"` (default) or `"warning"`; YAML loader rejects anything else.
- [ ] `tools/knowledge/lint/_detectors.py` defines `PlanPromoteDetector` (deterministic, `needs_llm=False`); reuses `blueprint_view.plan_provides_proof` and `_canonical_plan_for_target` matches the canonical-plan selection logic in `tools/knowledge/promote_via_plan.py`.
- [ ] `_default_detectors` instantiates the new detector with the threaded severity.
- [ ] `tests/test_lint_plan_promote.py` covers: nominal fire, severity escalation, severity validation, already-proved silence, staged-plan silence, plan-ancestor-unready silence, no-plan silence, non-theorem skip, multi-plan canonicalisation.
- [ ] `tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring` asserts on the eight-code set and severity threading.
- [ ] `tests/test_config.py` covers the new severity field.
- [ ] `docs/lint.md` documents all eight rule codes plus CLI / config / LLM gating.
- [ ] `AGENTS.md` has a Common Task Map row for `mdblueprint-lint`.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0; output may include new `LINT_PLAN_PROMOTE` info findings — capture them verbatim in the final report and do **NOT** silence them.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` output byte-identical.
- [ ] Five commits on `main` (config, detector, wiring, lint.md, AGENTS.md), no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint/_detectors.py` under 500 lines.
- [ ] No real `claude` subprocess spawned in any test.

## After PR 8

Issues #121 and #127 are ready to close. The final closing comments should reference (a) the complete rule list, (b) the doc location, and (c) the verification recipe under `AGENTS.md`'s Common Task Map.
