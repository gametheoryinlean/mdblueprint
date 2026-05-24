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
    """JSON-on-disk cache keyed by ``(detector_code, key)``.

    When ``cache_dir`` is ``None``, behaves as an in-memory dict (used for
    ``--no-cache``).
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
    """Cap the total number of LLM calls an entire ``Linter.run`` may make."""

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
        flips ``exhausted`` to True so callers can emit one info diagnostic.
        """
        if self._budget is None:
            self._spent += 1
            return True
        if self._spent < self._budget:
            self._spent += 1
            return True
        self._exhausted_emitted = True
        return False
