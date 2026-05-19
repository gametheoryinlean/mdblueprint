"""File-watcher utility for the dev server.

Watches the knowledge root for `.md` and `.yml` changes and fires a single
debounced callback. The callback runs on the watchdog Observer's worker
thread; consumers must handle their own synchronization.

Failures in the callback must not crash the Observer thread. The watcher
wraps the callback in a try/except and logs to stderr.
"""
from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


_WATCHED_SUFFIXES = (".md", ".yml", ".yaml")


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[], None], debounce_s: float = 0.3):
        self._on_change = on_change
        self._debounce_s = debounce_s
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = str(getattr(event, "src_path", ""))
        if not path.endswith(_WATCHED_SUFFIXES):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_s, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        try:
            self._on_change()
        except Exception as exc:
            print(
                f"[mdblueprint-watcher] callback raised: {exc!r}",
                file=sys.stderr,
            )


class KnowledgeWatcher:
    """Recursive filesystem watcher for a knowledge root."""

    def __init__(
        self,
        knowledge_root: Path,
        on_change: Callable[[], None],
        debounce_s: float = 0.3,
    ):
        self._root = knowledge_root
        self._handler = _ChangeHandler(on_change, debounce_s=debounce_s)
        self._observer = Observer()
        self._started = False

    def start(self) -> None:
        if self._started:
            raise RuntimeError("KnowledgeWatcher already started")
        self._observer.schedule(self._handler, str(self._root), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._started = False