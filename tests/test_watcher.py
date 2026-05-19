import threading
import time
from pathlib import Path

import pytest

from tools.knowledge.watcher import KnowledgeWatcher


@pytest.fixture
def watcher_factory(tmp_path: Path):
    started: list[KnowledgeWatcher] = []

    def make(on_change, debounce_s: float = 0.1) -> KnowledgeWatcher:
        w = KnowledgeWatcher(tmp_path, on_change, debounce_s=debounce_s)
        w.start()
        started.append(w)
        return w

    yield make, tmp_path

    for w in started:
        w.stop()


class TestFires:
    def test_md_change_fires_callback(self, watcher_factory):
        make, root = watcher_factory
        called = threading.Event()
        make(called.set)
        (root / "a.md").write_text("hello")
        assert called.wait(timeout=2.0)

    def test_yml_change_fires_callback(self, watcher_factory):
        make, root = watcher_factory
        called = threading.Event()
        make(called.set)
        (root / "mdblueprint.yml").write_text("site:\n  title: x\n")
        assert called.wait(timeout=2.0)

    def test_nested_md_fires(self, watcher_factory):
        make, root = watcher_factory
        called = threading.Event()
        make(called.set)
        nested = root / "nodes" / "topic"
        nested.mkdir(parents=True)
        (nested / "x.md").write_text("x")
        assert called.wait(timeout=2.0)


class TestIgnores:
    def test_txt_does_not_fire(self, watcher_factory):
        make, root = watcher_factory
        called = threading.Event()
        make(called.set)
        (root / "note.txt").write_text("ignore me")
        time.sleep(0.5)
        assert not called.is_set()

    def test_mkdir_does_not_fire(self, watcher_factory):
        make, root = watcher_factory
        called = threading.Event()
        make(called.set)
        (root / "newdir").mkdir()
        time.sleep(0.5)
        assert not called.is_set()


class TestDebounce:
    def test_rapid_writes_fire_once(self, watcher_factory):
        make, root = watcher_factory
        count = [0]
        ev = threading.Event()
        def on_change():
            count[0] += 1
            ev.set()
        make(on_change, debounce_s=0.2)
        for i in range(5):
            (root / f"f{i}.md").write_text(str(i))
        assert ev.wait(timeout=2.0)
        time.sleep(0.4)
        assert count[0] == 1

    def test_well_spaced_writes_fire_multiple(self, watcher_factory):
        make, root = watcher_factory
        count = [0]
        cv = threading.Condition()
        def on_change():
            with cv:
                count[0] += 1
                cv.notify_all()
        make(on_change, debounce_s=0.1)
        (root / "a.md").write_text("a")
        time.sleep(0.4)
        (root / "b.md").write_text("b")
        with cv:
            cv.wait_for(lambda: count[0] >= 2, timeout=2.0)
        assert count[0] >= 2


class TestErrorRecovery:
    def test_callback_exception_does_not_stop_watcher(self, watcher_factory):
        make, root = watcher_factory
        attempts = [0]
        ok = threading.Event()
        def on_change():
            attempts[0] += 1
            if attempts[0] == 1:
                raise RuntimeError("boom")
            ok.set()
        make(on_change, debounce_s=0.1)
        (root / "a.md").write_text("1")
        time.sleep(0.5)
        (root / "b.md").write_text("2")
        assert ok.wait(timeout=2.0)


class TestLifecycle:
    def test_double_start_raises(self, watcher_factory):
        make, _ = watcher_factory
        w = make(lambda: None)
        with pytest.raises(RuntimeError):
            w.start()

    def test_stop_then_no_fire(self, tmp_path):
        called = threading.Event()
        w = KnowledgeWatcher(tmp_path, called.set, debounce_s=0.1)
        w.start()
        w.stop()
        (tmp_path / "a.md").write_text("x")
        time.sleep(0.5)
        assert not called.is_set()

    def test_stop_is_idempotent(self, tmp_path):
        w = KnowledgeWatcher(tmp_path, lambda: None)
        w.stop()
        w.start()
        w.stop()
        w.stop()