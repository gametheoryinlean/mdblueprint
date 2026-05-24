# Blueprint Lint PR 6 — LLM Runner Cache + Detector 9 (semantic duplicate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the LLM-backed detector infrastructure (`_LintCache` plus per-call budget enforcement) and ship the first semantic-judgement detector, `SemanticDupDetector` (`LINT_SEMANTIC_DUP`, `needs_llm=True`). When `--llm` is unset, the detector remains gated off by the existing `Linter` plumbing. When `--llm` is set, the detector picks candidate pairs by re-running the fuzzy ratio at a lower threshold (default `0.75`), asks the model whether each pair states the same theorem, caches the per-pair JSON response, and respects `--llm-budget`.

**Architecture:**

- `_LintCache` (`tools/knowledge/lint/_cache.py`) — content-addressed JSON cache. One file per detector code under `--cache-dir`. Key = SHA-256 of `(detector_code, prompt_version, sorted_ids, content_hash)`; value = the parsed model response object plus the raw model text. Atomic write via temp-file rename.
- `_BudgetTracker` (small helper inside `_cache.py`) — counts LLM calls and short-circuits when the budget is hit.
- `SemanticDupDetector` (`tools/knowledge/lint/_detectors.py`) — pure dataclass with the same `Detector` protocol; takes `cache`, `budget_tracker`, `candidate_threshold` as constructor args. Its `run` walks the cache first, only calling `llm` on misses.
- `_default_detectors(config, *, lean_indexes=..., cache=..., budget=...)` grows two kwargs; `main()` constructs both based on `--cache-dir` / `--no-cache` / `--llm-budget`.

**Tech Stack:** Python 3.10+, stdlib (`hashlib`, `json`, `tempfile`, `pathlib`, `dataclasses`, `typing`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 6 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PRs 1-5 are on `main`. After PR 5, the lint package is:

```
tools/knowledge/lint/
    __init__.py     # public re-exports
    _core.py        # Detector protocol, Linter, renderers, CLI, _default_detectors, main
    _detectors.py   # 5 detectors + helpers (~372 lines)
```

`LintConfig` currently has only `fuzzy_threshold: float = 0.92`. PR 6 adds `semantic_candidate_threshold: float = 0.75`.

`Linter.run` already short-circuits `needs_llm=True` detectors when `self._llm is None` (see `_core.py` after PR 2). PR 6 inherits that gating for free — the cache and budget only matter once `--llm` is set.

The cache key includes a prompt-version constant so editing the prompt in a future change invalidates every cached row deterministically. `_LintCache` is dumb: it doesn't know about prompts or budgets, only the key/value contract. `_BudgetTracker` is similarly minimal.

Per the parent plan, semantic candidate pair selection re-runs the fuzzy ratio (already implemented in `_detectors._ratio`) at the lower `semantic_candidate_threshold`, then caps at `--llm-budget`. We pick candidates deterministically by `(ratio descending, then sorted ids ascending)` so re-runs with the same input choose the same pairs.

Defensive parsing: when the model returns malformed JSON, we emit one `info` per failed pair with the truncated raw text and skip the pair. Cached pairs whose value is "raw parse failure" are still cache hits — the model isn't retried until prompt-version changes or the cache is cleared.

## File Structure

- **Create**: `tools/knowledge/lint/_cache.py` — `_LintCache`, `_BudgetTracker`, `_content_hash`, `_PROMPT_VERSION_SEMANTIC_DUP` constant lives in `_detectors.py` though.
- **Modify**: `tools/knowledge/lint/_detectors.py` — append `SemanticDupDetector` plus its `_PROMPT_VERSION_SEMANTIC_DUP` constant.
- **Modify**: `tools/knowledge/lint/_core.py` — `_default_detectors(config, *, lean_indexes, cache, budget)` signature; `main()` builds cache + budget from CLI args.
- **Modify**: `tools/knowledge/lint/__init__.py` — re-export `SemanticDupDetector` (and `_LintCache` if tests want to drive it directly).
- **Modify**: `tools/knowledge/config.py` — add `semantic_candidate_threshold: float = 0.75` to `LintConfig`; extend `_parse_lint_config` to read it.
- **Create**: `tests/test_lint_cache.py` — pure `_LintCache` / `_BudgetTracker` tests with `tmp_path`.
- **Create**: `tests/test_lint_llm_semantic.py` — `SemanticDupDetector` end-to-end with fake `LlmRunner`.
- **Modify**: `tests/test_config.py` — round-trip the new threshold.
- **Modify**: `tests/test_lint_orchestrator.py` — `_default_detectors` wiring assertions grow `LINT_SEMANTIC_DUP`.

Projected sizes: `_cache.py` ~120 lines, `_detectors.py` ~480 lines (just over the per-file 400 target — flag if growth keeps pushing; consider further split in PR 7+).

---

### Task 1: `_LintCache` and `_BudgetTracker`

**Files:**
- Create: `tools/knowledge/lint/_cache.py`
- Create: `tests/test_lint_cache.py`

#### Step 1.1: Write the first failing tests

- [ ] Create `tests/test_lint_cache.py`:

```python
"""Tests for _LintCache and _BudgetTracker (PR 6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.knowledge.lint._cache import (
    _BudgetTracker,
    _LintCache,
    _content_hash,
)


class TestContentHash:
    def test_stable_across_invocations(self):
        a = _content_hash("hello\nworld\n")
        b = _content_hash("hello\nworld\n")
        assert a == b

    def test_changes_with_input(self):
        assert _content_hash("alpha") != _content_hash("beta")


class TestLintCache:
    def test_miss_then_hit(self, tmp_path: Path):
        cache = _LintCache(tmp_path)
        assert cache.get("LINT_SEMANTIC_DUP", "key-1") is None
        cache.put("LINT_SEMANTIC_DUP", "key-1", {"same": True, "raw": "..."})
        assert cache.get("LINT_SEMANTIC_DUP", "key-1") == {"same": True, "raw": "..."}

    def test_persists_across_instances(self, tmp_path: Path):
        first = _LintCache(tmp_path)
        first.put("LINT_SEMANTIC_DUP", "key-1", {"same": False})
        second = _LintCache(tmp_path)
        assert second.get("LINT_SEMANTIC_DUP", "key-1") == {"same": False}

    def test_distinct_detector_codes_do_not_collide(self, tmp_path: Path):
        cache = _LintCache(tmp_path)
        cache.put("LINT_SEMANTIC_DUP", "key-1", {"same": True})
        cache.put("LINT_LEAN_ALIGN", "key-1", {"aligned": False})
        assert cache.get("LINT_SEMANTIC_DUP", "key-1") == {"same": True}
        assert cache.get("LINT_LEAN_ALIGN", "key-1") == {"aligned": False}

    def test_atomic_write_does_not_leave_partial_files(self, tmp_path: Path):
        cache = _LintCache(tmp_path)
        cache.put("LINT_SEMANTIC_DUP", "key-1", {"same": True})
        # Only the finalized file should remain; no `.tmp` siblings.
        siblings = list(tmp_path.glob("*"))
        for s in siblings:
            assert not s.name.endswith(".tmp"), f"leftover temp file: {s}"

    def test_disabled_cache_is_in_memory_only(self, tmp_path: Path):
        # When constructed with cache_dir=None, _LintCache stays purely in-memory
        # so --no-cache callers still benefit from intra-run dedupe but nothing
        # is persisted to disk.
        cache = _LintCache(cache_dir=None)
        cache.put("LINT_SEMANTIC_DUP", "key-1", {"same": True})
        assert cache.get("LINT_SEMANTIC_DUP", "key-1") == {"same": True}
        # Nothing on disk.
        assert not any(tmp_path.iterdir())

    def test_round_trip_preserves_nested_structures(self, tmp_path: Path):
        cache = _LintCache(tmp_path)
        payload = {
            "same": True,
            "reason": "Both statements assert uniqueness of the identity.",
            "raw": '{"same": true, "reason": "..."}',
            "model": "claude-sonnet-4-6",
            "ids": ["alg.x", "alg.y"],
        }
        cache.put("LINT_SEMANTIC_DUP", "key-deep", payload)
        recovered = _LintCache(tmp_path).get("LINT_SEMANTIC_DUP", "key-deep")
        assert recovered == payload


class TestBudgetTracker:
    def test_unlimited_when_budget_is_none(self):
        tracker = _BudgetTracker(budget=None)
        for _ in range(1000):
            assert tracker.try_spend()
        assert tracker.spent == 1000

    def test_zero_budget_returns_false_immediately(self):
        tracker = _BudgetTracker(budget=0)
        assert tracker.try_spend() is False
        assert tracker.spent == 0

    def test_positive_budget_caps(self):
        tracker = _BudgetTracker(budget=3)
        assert tracker.try_spend() is True
        assert tracker.try_spend() is True
        assert tracker.try_spend() is True
        assert tracker.try_spend() is False
        assert tracker.spent == 3
        assert tracker.exhausted is True

    def test_exhausted_false_until_hit(self):
        tracker = _BudgetTracker(budget=2)
        assert tracker.exhausted is False
        tracker.try_spend()
        assert tracker.exhausted is False
        tracker.try_spend()
        # After the budget is reached, the next try is the trigger.
        assert tracker.exhausted is False
        tracker.try_spend()
        assert tracker.exhausted is True
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_cache.py -q`
- [ ] Expected: `ImportError` on `_LintCache` / `_BudgetTracker` / `_content_hash`.

#### Step 1.2: Implement the cache

Create `tools/knowledge/lint/_cache.py`:

```python
"""Content-addressed JSON cache and budget tracker for LLM-backed lint detectors.

Both helpers are deliberately simple and detector-agnostic — they speak
only in opaque (code, key, value) tuples so any future detector can share
the infrastructure without bespoke key shapes.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def _content_hash(text: str) -> str:
    """Stable SHA-256 hex digest of the input text. Independent of locale or platform."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _LintCache:
    """JSON-on-disk cache keyed by `(detector_code, key)`.

    When `cache_dir` is `None`, behaves as an in-memory dict (used for
    `--no-cache`).
    """

    def __init__(self, cache_dir: Path | None) -> None:
        self._cache_dir = cache_dir
        self._memory: dict[tuple[str, str], dict] = {}
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for path in cache_dir.glob("*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                code = path.stem
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        if isinstance(value, dict):
                            self._memory[(code, key)] = value

    def get(self, code: str, key: str) -> dict | None:
        return self._memory.get((code, key))

    def put(self, code: str, key: str, value: dict) -> None:
        self._memory[(code, key)] = value
        if self._cache_dir is None:
            return
        rows = {
            entry_key: entry_value
            for (entry_code, entry_key), entry_value in self._memory.items()
            if entry_code == code
        }
        self._atomic_write(self._cache_dir / f"{code}.json", rows)

    @staticmethod
    def _atomic_write(target: Path, payload: dict) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass


class _BudgetTracker:
    """Cap the total number of LLM calls an entire `Linter.run` may make."""

    def __init__(self, budget: int | None) -> None:
        self._budget = budget
        self._spent = 0
        self._exhausted_emitted = False

    @property
    def spent(self) -> int:
        return self._spent

    @property
    def exhausted(self) -> bool:
        # True only on the first try after the budget was reached, so the
        # caller can emit a single "budget exhausted" info diagnostic.
        return self._exhausted_emitted

    def try_spend(self) -> bool:
        """Return True if the caller may make one more LLM call.

        Returns False once the budget is exhausted. The first False return
        flips `exhausted` to True so callers can emit one info diagnostic.
        """
        if self._budget is None:
            self._spent += 1
            return True
        if self._spent < self._budget:
            self._spent += 1
            return True
        self._exhausted_emitted = True
        return False
```

#### Step 1.3: Run the cache tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_cache.py -q`
- [ ] Expected: every test passes.

#### Step 1.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: 605 + cache tests = ~622 passing.

#### Step 1.5: Commit Task 1

```bash
git add tools/knowledge/lint/_cache.py tests/test_lint_cache.py
git commit -m "$(cat <<'EOF'
feat(lint): add _LintCache + _BudgetTracker for LLM-backed detectors

_LintCache stores one JSON file per detector code under --cache-dir,
keyed by an opaque (code, key) pair. Writes are atomic via mkstemp +
os.replace; reads fall back gracefully on malformed files. With
cache_dir=None it degrades to an in-memory dict so --no-cache still
gets intra-run dedupe without touching disk.

_BudgetTracker caps total LLM calls per Linter.run. budget=None means
unlimited; budget=0 disallows everything; the first try after the
limit is hit flips the `exhausted` flag so callers can emit a single
budget-exhausted info diagnostic.

Both helpers are detector-agnostic — they speak only in opaque
(code, key, value) tuples and have no awareness of prompts or
diagnostics. Issue #121, PR 6.
EOF
)"
```

---

### Task 2: `LintConfig.semantic_candidate_threshold`

**Files:**
- Modify: `tools/knowledge/config.py`
- Modify: `tests/test_config.py`

#### Step 2.1: Write the first failing test

Append to `tests/test_config.py`:

```python
def test_load_project_config_reads_semantic_candidate_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Semantic Threshold Test\n"
        "lint:\n"
        "  fuzzy_threshold: 0.91\n"
        "  semantic_candidate_threshold: 0.65\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.fuzzy_threshold == 0.91
    assert cfg.lint.semantic_candidate_threshold == 0.65


def test_load_project_config_uses_default_semantic_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Default Semantic Threshold\n",
        encoding="utf-8",
    )
    cfg = load_project_config(tmp_path)
    assert cfg.lint.semantic_candidate_threshold == 0.75


def test_load_project_config_rejects_bad_semantic_threshold(tmp_path: Path) -> None:
    from tools.knowledge.config import load_project_config

    (tmp_path / "mdblueprint.yml").write_text(
        "site:\n  title: Bad Semantic Threshold\n"
        "lint:\n  semantic_candidate_threshold: 2.0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="semantic_candidate_threshold"):
        load_project_config(tmp_path)
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py::test_load_project_config_reads_semantic_candidate_threshold -q`
- [ ] Expected: `AttributeError` for the missing field.

#### Step 2.2: Extend `LintConfig` and the parser

In `tools/knowledge/config.py`:

```python
@dataclass(frozen=True)
class LintConfig:
    fuzzy_threshold: float = 0.92
    semantic_candidate_threshold: float = 0.75
```

Update `_parse_lint_config` to accept the new field with the same shape of validation:

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
    return LintConfig(
        fuzzy_threshold=fuzzy_threshold,
        semantic_candidate_threshold=semantic_candidate_threshold,
    )


def _parse_unit_interval(value: Any, *, path: Path, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(
            f"Project config lint.{field} must be a number between 0 and 1: {path}"
        )
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(
            f"Project config lint.{field} must be between 0 and 1, got {value}: {path}"
        )
    return value
```

(If `_parse_unit_interval` is too much of a refactor for this task, inline the same validation. The behavior must match.)

#### Step 2.3: Run config tests + full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/test_config.py -q`
- [ ] Expected: all tests pass, including the three new ones.
- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 2.4: Commit Task 2

```bash
git add tools/knowledge/config.py tests/test_config.py
git commit -m "$(cat <<'EOF'
feat(config): add LintConfig.semantic_candidate_threshold (default 0.75)

Drives the candidate pair set for the upcoming SemanticDupDetector:
re-runs the fuzzy SequenceMatcher ratio at the lower threshold to
select pairs that survived fuzzy but might still be semantic
duplicates. Validation reuses the [0, 1] guard via a shared
_parse_unit_interval helper. Issue #121, PR 6.
EOF
)"
```

---

### Task 3: `SemanticDupDetector`

**Files:**
- Modify: `tools/knowledge/lint/_detectors.py`
- Modify: `tools/knowledge/lint/__init__.py`
- Create: `tests/test_lint_llm_semantic.py`

#### Step 3.1: Write the first failing tests

- [ ] Create `tests/test_lint_llm_semantic.py`:

```python
"""Tests for SemanticDupDetector (PR 6)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import SemanticDupDetector
from tools.knowledge.lint._cache import _BudgetTracker, _LintCache
from tools.knowledge.models import Node


@dataclass
class _FakeRunner:
    """LlmRunner that returns a fixed response and records every prompt."""
    response: str
    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _node(node_id: str, title: str, *, status: str = "admitted", body: str = "") -> Node:
    return Node(id=node_id, title=title, kind="theorem", status=status, body=body)


def _pair_near_fuzzy_threshold() -> tuple[Node, Node]:
    # ~0.78 similarity in titles — above semantic_candidate_threshold=0.75
    # but below fuzzy_threshold=0.92.
    a = _node("alg.x", "Identity element of a group is unique")
    b = _node("alg.y", "The identity in a group is unique element")
    return a, b


class TestPromptShape:
    def test_prompt_contains_both_statements_and_json_instruction(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "different"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        det.run([a, b], graph, llm=runner)
        assert len(runner.prompts) == 1
        prompt = runner.prompts[0]
        assert "alg.x" in prompt
        assert "alg.y" in prompt
        assert a.title in prompt
        assert b.title in prompt
        # The prompt must ask for JSON specifically so parsing is deterministic.
        assert "json" in prompt.lower()
        # And it should name the expected keys.
        assert '"same"' in prompt
        assert '"reason"' in prompt


class TestDecisionPaths:
    def test_same_true_emits_warning_with_related(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(
            response='{"same": true, "reason": "Both state uniqueness of the identity."}'
        )
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_SEMANTIC_DUP"
        # Source node is the lex-smaller of the pair; related is the other.
        assert d.node_id == "alg.x"
        assert d.related == ("alg.y",)
        # Message echoes the model's reason for traceability.
        assert "uniqueness of the identity" in d.message.lower()

    def test_same_false_emits_no_warning(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "different facts"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []

    def test_malformed_response_emits_one_info(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response="not valid json at all")
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"
        assert d.code == "LINT_SEMANTIC_DUP"
        assert "parse" in d.message.lower() or "json" in d.message.lower()

    def test_missing_same_key_treated_as_malformed(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"answer": "yes"}')  # wrong key
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert len(diags) == 1
        assert diags[0].level == "info"


class TestCandidateSelection:
    def test_pair_below_candidate_threshold_is_not_judged(self, tmp_path: Path):
        a = _node("alg.x", "Group identity is unique")
        b = _node("ana.z", "Cauchy-Schwarz inequality")  # very different
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "should not be asked"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []
        assert runner.prompts == []

    def test_only_admitted_nodes_are_candidates(self, tmp_path: Path):
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity in a group is unique element", status="staged")
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        assert det.run([a, b], graph, llm=runner) == []
        assert runner.prompts == []


class TestCaching:
    def test_second_run_with_same_inputs_does_not_call_llm(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner1 = _FakeRunner(response='{"same": true, "reason": "Same."}')
        cache = _LintCache(tmp_path)
        det1 = SemanticDupDetector(
            cache=cache, budget=_BudgetTracker(budget=10), candidate_threshold=0.75,
        )
        det1.run([a, b], graph, llm=runner1)
        assert runner1.prompts  # first run did call

        # Fresh runner; same cache directory.
        runner2 = _FakeRunner(response='{"same": false, "reason": "should not be asked"}')
        det2 = SemanticDupDetector(
            cache=_LintCache(tmp_path),  # cold instance, warm on-disk cache
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        diags = det2.run([a, b], graph, llm=runner2)
        # Cache hit: zero new LLM calls, but the warning is still produced from
        # the cached `same: true` decision.
        assert runner2.prompts == []
        assert len(diags) == 1
        assert diags[0].level == "warning"

    def test_no_cache_mode_still_dedupes_within_a_run(self, tmp_path: Path):
        # A second identical pair in the same run should reuse the cached
        # answer from the first call even with cache_dir=None.
        a = _node("alg.x", "Identity element of a group is unique")
        b = _node("alg.y", "The identity in a group is unique element")
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": false, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(cache_dir=None),
            budget=_BudgetTracker(budget=10),
            candidate_threshold=0.75,
        )
        # Two consecutive runs against the same fixture; expect one LLM call.
        det.run([a, b], graph, llm=runner)
        det.run([a, b], graph, llm=runner)
        assert len(runner.prompts) == 1


class TestBudget:
    def test_zero_budget_emits_info_and_skips_llm(self, tmp_path: Path):
        a, b = _pair_near_fuzzy_threshold()
        graph, _ = build_graph([a, b])
        runner = _FakeRunner(response='{"same": true, "reason": "should not be called"}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=0),
            candidate_threshold=0.75,
        )
        diags = det.run([a, b], graph, llm=runner)
        assert runner.prompts == []
        # One info "budget exhausted" diagnostic; no warnings.
        assert any(d.level == "info" and "budget" in d.message.lower() for d in diags)
        assert not any(d.level == "warning" for d in diags)

    def test_budget_one_calls_at_most_once_across_many_candidates(self, tmp_path: Path):
        nodes: list[Node] = []
        for i in range(4):
            nodes.append(_node(f"alg.x{i}", f"Identity element of a group is unique variant {i}"))
            nodes.append(_node(f"alg.y{i}", f"The identity in a group is unique element variant {i}"))
        graph, _ = build_graph(nodes)
        runner = _FakeRunner(response='{"same": true, "reason": "..."}')
        det = SemanticDupDetector(
            cache=_LintCache(tmp_path),
            budget=_BudgetTracker(budget=1),
            candidate_threshold=0.75,
        )
        det.run(nodes, graph, llm=runner)
        assert len(runner.prompts) == 1
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_llm_semantic.py -q`
- [ ] Expected: `ImportError: cannot import name 'SemanticDupDetector'`.

#### Step 3.2: Implement the detector

Append to `tools/knowledge/lint/_detectors.py`:

```python
import json as _json_stdlib

from tools.knowledge.lint._cache import _BudgetTracker, _LintCache, _content_hash


_PROMPT_VERSION_SEMANTIC_DUP = "v1"
_BUDGET_INFO_MESSAGE = "LLM budget exhausted; skipped remaining LINT_SEMANTIC_DUP candidates"


def _semantic_dup_prompt(a: Node, b: Node) -> str:
    """Build the per-pair prompt; the exact text is part of the cache key
    via _PROMPT_VERSION_SEMANTIC_DUP, so any wording change should bump
    the version constant."""
    a_stmt = _statement_text(a) or a.body or ""
    b_stmt = _statement_text(b) or b.body or ""
    return (
        "Two mathematical knowledge-base nodes are below. Decide whether they "
        "state the same mathematical claim (allowing renaming and notational "
        "differences). Reply with a single JSON object of the form "
        '{"same": <bool>, "reason": "<one-sentence justification>"}.\n\n'
        f"Node 1 id: {a.id}\nTitle: {a.title}\nStatement:\n{a_stmt}\n\n"
        f"Node 2 id: {b.id}\nTitle: {b.title}\nStatement:\n{b_stmt}\n\n"
        "Return only the JSON object."
    )


def _semantic_dup_cache_key(a: Node, b: Node) -> str:
    body = "\n".join([
        _PROMPT_VERSION_SEMANTIC_DUP,
        a.id, a.title, _statement_text(a) or a.body or "",
        b.id, b.title, _statement_text(b) or b.body or "",
    ])
    return _content_hash(body)


def _parse_semantic_dup_response(raw: str) -> tuple[bool | None, str]:
    """Return (same | None on parse failure, reason)."""
    try:
        payload = _json_stdlib.loads(raw)
    except Exception:
        return None, raw[:200]
    if not isinstance(payload, dict) or "same" not in payload:
        return None, raw[:200]
    same = payload.get("same")
    if not isinstance(same, bool):
        return None, raw[:200]
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        reason = ""
    return same, reason


@dataclass
class SemanticDupDetector:
    """Ask an LLM whether candidate near-duplicate pairs really state the same theorem."""

    cache: _LintCache
    budget: _BudgetTracker
    candidate_threshold: float = 0.75
    code: str = "LINT_SEMANTIC_DUP"
    needs_llm: bool = True

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        if llm is None:
            return []

        admitted = sorted(
            (n for n in nodes if n.status in ADMITTED_STATUSES),
            key=lambda n: n.id,
        )
        # Candidate pair set: (a, b) with a.id < b.id and fuzzy ratio >= candidate_threshold.
        candidates: list[tuple[float, Node, Node]] = []
        for index, a in enumerate(admitted):
            a_title = _normalize(a.title)
            a_stmt = _normalize(_statement_text(a))
            for b in admitted[index + 1:]:
                b_title = _normalize(b.title)
                score = _ratio(a_title, b_title)
                if score < self.candidate_threshold:
                    b_stmt = _normalize(_statement_text(b))
                    if a_stmt and b_stmt:
                        score = max(score, _ratio(a_stmt, b_stmt))
                if score >= self.candidate_threshold:
                    candidates.append((score, a, b))

        # Deterministic order: highest ratio first, ties by sorted ids.
        candidates.sort(key=lambda triple: (-triple[0], triple[1].id, triple[2].id))

        out: list[Diagnostic] = []
        budget_already_reported = False
        for _, a, b in candidates:
            key = _semantic_dup_cache_key(a, b)
            cached = self.cache.get(self.code, key)
            if cached is None:
                if not self.budget.try_spend():
                    if not budget_already_reported:
                        out.append(Diagnostic(
                            level="info",
                            node_id="",
                            message=_BUDGET_INFO_MESSAGE,
                            code=self.code,
                        ))
                        budget_already_reported = True
                    break
                raw = llm(_semantic_dup_prompt(a, b))
                same, reason = _parse_semantic_dup_response(raw)
                cached = {"same": same, "reason": reason, "raw": raw[:2000]}
                self.cache.put(self.code, key, cached)

            same = cached.get("same")
            reason = cached.get("reason", "")
            if same is None:
                out.append(Diagnostic(
                    level="info",
                    node_id=a.id,
                    message=(
                        f"could not parse JSON from LLM response for semantic-dup "
                        f"judgement of {a.id!r} vs {b.id!r}; raw: {reason}"
                    ),
                    file_path=a.file_path,
                    code=self.code,
                    related=(b.id,),
                ))
                continue
            if same:
                out.append(Diagnostic(
                    level="warning",
                    node_id=a.id,
                    message=(
                        f"LLM judged {a.id!r} and {b.id!r} as the same theorem: {reason}"
                    ),
                    file_path=a.file_path,
                    code=self.code,
                    related=(b.id,),
                ))
        return out
```

#### Step 3.3: Re-export

- [ ] Add `SemanticDupDetector` to the import line in `tools/knowledge/lint/__init__.py` and to `__all__`.

#### Step 3.4: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_llm_semantic.py -q`
- [ ] Expected: every test passes. No real `claude` subprocess is invoked.

#### Step 3.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 3.6: Commit Task 3

```bash
git add tools/knowledge/lint/_detectors.py tools/knowledge/lint/__init__.py tests/test_lint_llm_semantic.py
git commit -m "$(cat <<'EOF'
feat(lint): add SemanticDupDetector (LINT_SEMANTIC_DUP)

For each admitted-pair whose fuzzy ratio reaches the (lower)
semantic_candidate_threshold, build a JSON-prompt and ask the
LlmRunner whether they state the same theorem. Decisions are
content-hashed into _LintCache so repeated runs reuse prior
judgments; the per-run _BudgetTracker caps total LLM calls and
emits one budget-exhausted info diagnostic when reached.

Parse failures (malformed JSON, missing 'same' key, wrong types)
degrade to info-level diagnostics rather than warnings, with the
truncated raw response in the message body for traceability. Cache
entries from a failed parse persist; the model is re-asked only
when _PROMPT_VERSION_SEMANTIC_DUP is bumped or the cache is
cleared. Issue #121, PR 6.
EOF
)"
```

---

### Task 4: Wire into `_default_detectors` and `main()`

**Files:**
- Modify: `tools/knowledge/lint/_core.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 4.1: Update `TestDefaultDetectorsWiring`

In `tests/test_lint_orchestrator.py`:

```python
class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            LeanRefKindDetector,
            SemanticDupDetector,
            StagedAdmittedOverlapDetector,
            _default_detectors,
        )

        detectors = _default_detectors(LintConfig(fuzzy_threshold=0.77, semantic_candidate_threshold=0.6))
        codes = {d.code for d in detectors}
        # PR 3..6 contributors:
        assert codes >= {"LINT_FUZZY_DUP", "LINT_STAGED_OVERLAP",
                          "LINT_REDUNDANT_DEP", "LINT_ORPHAN",
                          "LINT_LEAN_KIND", "LINT_SEMANTIC_DUP"}

        fuzzy = next(d for d in detectors if isinstance(d, FuzzyTitleDupDetector))
        overlap = next(d for d in detectors if isinstance(d, StagedAdmittedOverlapDetector))
        semantic = next(d for d in detectors if isinstance(d, SemanticDupDetector))
        assert fuzzy.threshold == 0.77
        assert overlap.threshold == 0.77
        assert semantic.candidate_threshold == 0.6

    def test_default_detectors_accept_cache_and_budget(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import SemanticDupDetector, _default_detectors
        from tools.knowledge.lint._cache import _BudgetTracker, _LintCache

        cache = _LintCache(tmp_path)
        budget = _BudgetTracker(budget=42)
        detectors = _default_detectors(LintConfig(), cache=cache, budget=budget)
        semantic = next(d for d in detectors if isinstance(d, SemanticDupDetector))
        assert semantic.cache is cache
        assert semantic.budget is budget
```

#### Step 4.2: Update `_default_detectors`

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
    cfg = config if config is not None else _LintConfig()
    cache = cache if cache is not None else _LC(cache_dir=None)
    budget = budget if budget is not None else _BT(budget=None)
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
        LeanRefKindDetector(indexes=lean_indexes),
        SemanticDupDetector(
            cache=cache,
            budget=budget,
            candidate_threshold=cfg.semantic_candidate_threshold,
        ),
    ]
```

#### Step 4.3: Update `main()` to construct cache and budget

```python
def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    from tools.knowledge.config import load_project_config
    from tools.knowledge.lean_index import index_lean_project
    from tools.knowledge.lint._cache import _BudgetTracker, _LintCache

    config = load_project_config(args.knowledge_root)

    lean_indexes: dict[str, "LeanIndex"] = {}
    for repo_id, repo in config.lean.repositories.items():
        if not repo.local_path.exists():
            continue
        try:
            lean_indexes[repo_id] = index_lean_project(repo.local_path, repository=repo)
        except Exception:
            continue
    if config.lean.default_repository and config.lean.default_repository in lean_indexes:
        lean_indexes.setdefault("default", lean_indexes[config.lean.default_repository])

    cache_dir = None if args.no_cache else args.cache_dir
    cache = _LintCache(cache_dir=cache_dir)
    budget = _BudgetTracker(budget=args.llm_budget)

    llm: LlmRunner | None = None
    if args.llm:
        llm = _make_claude_cli_runner(model=args.model)

    linter = Linter(
        detectors=_default_detectors(
            config.lint,
            lean_indexes=lean_indexes or None,
            cache=cache,
            budget=budget,
        ),
        llm=llm,
    )
    diags = linter.run(args.knowledge_root)
    output = render_json(diags) if args.json else render_text(diags)
    print(output)
    if any(d.level == "error" for d in diags):
        return 1
    if args.strict_warnings and any(d.level == "warning" for d in diags):
        return 1
    return 0
```

#### Step 4.4: Smoke

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: Same output as PR 5 (2 LINT_REDUNDANT_DEP + 1 LINT_LEAN_KIND info; no LINT_SEMANTIC_DUP because `--llm` is not set so `needs_llm=True` detectors are gated off by `Linter.run`). Exit 0.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --no-cache`
- [ ] Expected: Same output, no `.mdblueprint/lint-cache/` directory created.
- [ ] Run: `uv run mdblueprint-lint docs/knowledge --llm-budget 0`
- [ ] Expected: Same output (no `--llm` ⇒ semantic detector still gated off).

#### Step 4.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 4.6: `mdblueprint-check` byte-identical

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output.

#### Step 4.7: Commit Task 4

```bash
git add tools/knowledge/lint/_core.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): thread cache, budget, and SemanticDupDetector through main()

_default_detectors grows (cache, budget) kwargs; main() builds a
_LintCache from --cache-dir / --no-cache and a _BudgetTracker from
--llm-budget, then passes both into the default detector list. The
semantic detector remains gated off by Linter.run unless --llm is
set, so the bundled-example smoke output is unchanged. Issue #121,
PR 6.
EOF
)"
```

---

## Definition of Done

- [ ] `tools/knowledge/lint/_cache.py` defines `_LintCache` (atomic write, disk + memory modes), `_BudgetTracker` (None / 0 / positive), `_content_hash` (stable SHA-256 hex).
- [ ] `LintConfig.semantic_candidate_threshold: float = 0.75` parses from YAML and validates as a unit interval.
- [ ] `SemanticDupDetector` (`needs_llm=True`) picks candidate pairs at the lower threshold, prompts the LLM with a JSON-output instruction, caches every decision keyed by a prompt-version + content hash, respects a budget, and falls back to info diagnostics on parse failures.
- [ ] `_default_detectors(config, *, lean_indexes, cache, budget)` instantiates the semantic detector with the threaded `cache` and `budget`.
- [ ] `main()` builds the cache and budget from CLI flags and threads them.
- [ ] `tests/test_lint_cache.py` covers content-hash stability, cache miss/hit/persist/atomic-write/disabled, and the three budget modes.
- [ ] `tests/test_lint_llm_semantic.py` covers prompt shape, all three decision paths (same / different / malformed), candidate selection threshold, status filter, cache reuse across processes and within a process, and budget enforcement.
- [ ] `tests/test_config.py` covers the new threshold.
- [ ] `tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring` asserts on the six-code set and the cache/budget threading.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0 with the same output as PR 5 (semantic detector gated off without `--llm`).
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` byte-identical.
- [ ] Four commits on `main`, no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint/_detectors.py` under 500 lines (allowing some growth past 400 — the per-file split threshold from the parent plan is approximate; PR 7 may need to factor).
- [ ] No real `claude` subprocess is spawned anywhere in the test suite.

## Hand-off to PR 7

PR 7 (`LeanAlignmentLlmDetector`, code `LINT_LEAN_ALIGN`) mirrors PR 6's structure: same `_LintCache` + `_BudgetTracker` infrastructure, a different per-prompt content hash. The prompt covers a single node's `## Statement` vs the resolved Lean signature from the LeanIndex; the result is `{"aligned": bool, "reason": str}`. If `_detectors.py` grows past 500 lines, PR 7 should split semantic and Lean-alignment detectors into `tools/knowledge/lint/_llm.py` first.
