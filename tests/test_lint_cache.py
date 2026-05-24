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
