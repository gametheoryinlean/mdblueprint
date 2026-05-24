# Blueprint Lint PR 4 — Detectors 3 + 4 (redundant deps + orphans) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two pure graph-shape detectors to `mdblueprint-lint`:

- `RedundantDepDetector` (code `LINT_REDUNDANT_DEP`) — for every direct edge `u → v`, BFS from `u` over the remaining edges of the DAG; if `v` is still reachable, the edge `u → v` is redundant. Emits `info`.
- `OrphanDetector` (code `LINT_ORPHAN`) — emits `info` for each node with `in_degree == 0 and out_degree == 0`. No exception list this PR (parent plan Open Question #1 tracks the design space).

Both are deterministic, stdlib-only, and plug into `_default_detectors(config)` next to PR 3's detectors. The bundled example continues to lint cleanly at default settings.

**Architecture:** Both detectors live in `tools/knowledge/lint.py`. They read structural information off `KnowledgeGraph.edges` (dependent → dependencies adjacency, per `tools/knowledge/graph.py:13-15`) and `KnowledgeGraph.reverse_edges`. Neither needs LLM; neither takes a threshold; neither writes back. The Detector `Protocol` is unchanged.

**Tech Stack:** Python 3.10+, stdlib (`collections.deque` for BFS, `dataclasses`, `typing`), pytest. No new dependencies.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 4 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PR 1 (Diagnostic extension), PR 2 (Linter + renderers + CLI), and PR 3 (FuzzyTitleDup + StagedAdmittedOverlap) are all on `main`. After PR 3:

- `tools/knowledge/lint.py` is 330 lines.
- `_default_detectors(config: LintConfig | None)` returns `[FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold), StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold)]`.
- The bundled `docs/knowledge` lints clean.

PR 4 appends two more detectors to that list. No infrastructure change, no config change.

Real APIs the detectors use:

- `KnowledgeGraph.edges: dict[str, list[str]]` — adjacency keyed by **dependent** node id; values are the node ids listed in that node's `uses:` (see `graph.py:14` and `graph.py:51`). So `edges[u]` is the set of nodes `u` depends on.
- `KnowledgeGraph.reverse_edges: dict[str, list[str]]` — same map inverted; `reverse_edges[v]` is the set of nodes that depend on `v`.
- "Direct edge `u → v`" in the parent plan's spec means: in the user-facing dependency direction (prerequisite → consequence). Under the in-memory convention, that is the relation `v depends on u`, i.e. `u in edges[v]`. **The detector must reason in the user-facing direction**, so for the BFS step, traversing `edges` from a node walks toward that node's prerequisites (its uses).

Concrete restatement of the redundant-dep rule in the in-memory adjacency direction:

> For each `(v, u)` pair such that `u in edges[v]` (i.e. `v` directly uses `u`), check whether there is a path of length ≥ 2 in the `uses` graph from `v` to `u` that does not pass through the direct edge `v → u`. If such a path exists, the direct edge `v → u` is redundant: it can be removed because the prerequisite is already pulled in transitively.

The diagnostic should describe this in user-facing language: the *direct dependency* on the prerequisite is redundant because the prerequisite is already reachable through other dependencies. Both endpoints appear in the message and `related` contains the prerequisite node id (`u`).

Orphan rule is direction-free: a node with no `uses` *and* nothing using it has `in_degree == 0 and out_degree == 0` under either convention.

## File Structure

- **Create**: none.
- **Modify**: `tools/knowledge/lint.py` — append `RedundantDepDetector` and `OrphanDetector`; extend `_default_detectors(config)` to include both.
- **Create**: `tests/test_lint_structure.py` — TDD coverage for both detectors with hand-crafted `Node` fixtures.
- **Modify**: `tests/test_lint_orchestrator.py` — update the `TestDefaultDetectorsWiring` expectation set so the new codes appear; keep the bundled-example smoke assertion.

After PR 4, `tools/knowledge/lint.py` is projected at ~390 lines (still under the 400-line split threshold, but only just — flag if it overshoots).

---

### Task 1: `RedundantDepDetector`

**Files:**
- Modify: `tools/knowledge/lint.py`
- Create: `tests/test_lint_structure.py`

#### Step 1.1: Write the first failing tests

- [ ] Create `tests/test_lint_structure.py`:

```python
"""Tests for structural detectors (PR 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lint import OrphanDetector, RedundantDepDetector
from tools.knowledge.models import Node


def _node(node_id: str, *, kind: str = "theorem", status: str = "admitted", uses: list[str] | None = None) -> Node:
    return Node(id=node_id, title=node_id, kind=kind, status=status, uses=list(uses or []))


class TestRedundantDepDetector:
    def test_direct_dep_redundant_when_transitive_path_exists(self):
        # User-facing direction: a -> b -> c, plus the extra direct a -> c.
        # In the YAML convention that means:
        #   c.uses = [a, b]   (c directly depends on both a and b)
        #   b.uses = [a]      (b depends on a)
        # The direct c.uses entry "a" is redundant because c -> b -> a already exists.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.a", "topic.b"])
        graph, diags = build_graph([a, b, c])
        assert diags == []

        det = RedundantDepDetector()
        out = det.run([a, b, c], graph, llm=None)
        assert len(out) == 1
        d = out[0]
        assert d.level == "info"
        assert d.code == "LINT_REDUNDANT_DEP"
        # The diagnostic attaches to the dependent end (c); related names the redundant prerequisite (a).
        assert d.node_id == "topic.c"
        assert d.related == ("topic.a",)
        # Message names both endpoints for human readability.
        assert "topic.a" in d.message
        assert "topic.c" in d.message

    def test_no_findings_on_simple_chain(self):
        # a -> b -> c with no redundant direct edge.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.b"])
        graph, _ = build_graph([a, b, c])
        assert RedundantDepDetector().run([a, b, c], graph, llm=None) == []

    def test_no_findings_when_only_path_is_the_direct_edge(self):
        # Tree with diamond removed: c depends on a and on b independently;
        # neither a nor b reach each other. No redundancy.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", kind="definition")
        c = _node("topic.c", uses=["topic.a", "topic.b"])
        graph, _ = build_graph([a, b, c])
        assert RedundantDepDetector().run([a, b, c], graph, llm=None) == []

    def test_diamond_with_redundant_skip_level(self):
        #       a
        #      / \
        #     b   c
        #      \ /
        #       d  + extra d -> a (redundant: d -> b -> a and d -> c -> a)
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        c = _node("topic.c", uses=["topic.a"])
        d = _node("topic.d", uses=["topic.a", "topic.b", "topic.c"])
        graph, _ = build_graph([a, b, c, d])
        out = RedundantDepDetector().run([a, b, c, d], graph, llm=None)
        # Only d -> a is redundant. d -> b and d -> c are still the unique path to those.
        assert len(out) == 1
        assert (out[0].node_id, out[0].related) == ("topic.d", ("topic.a",))

    def test_self_loop_safety(self):
        # build_graph rejects cycles (including self-loops); this test guards
        # against the detector relying on cycle-free input regression-style.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        # Drive the detector with a hand-mutated edges entry just to confirm
        # the BFS terminates even if the input graph somehow contained one.
        graph.edges["topic.b"] = ["topic.a"]  # idempotent re-assignment
        det = RedundantDepDetector()
        assert det.run([a, b], graph, llm=None) == []
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_structure.py -q`
- [ ] Expected: `ImportError: cannot import name 'RedundantDepDetector' from 'tools.knowledge.lint'`.

#### Step 1.2: Implement the detector

Append to `tools/knowledge/lint.py` (after `StagedAdmittedOverlapDetector`, before `_default_detectors`):

```python
from collections import deque


@dataclass
class RedundantDepDetector:
    """Flag direct `uses` edges that are already implied by a transitive path."""

    code: str = "LINT_REDUNDANT_DEP"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        out: list[Diagnostic] = []
        # Iterate in deterministic order so diagnostic ordering is stable.
        for dependent_id in sorted(graph.edges):
            direct_deps = sorted(graph.edges.get(dependent_id, ()))
            if len(direct_deps) < 2:
                # A node with at most one direct dependency cannot have a
                # redundant direct edge: there is no second path candidate.
                continue
            direct_set = set(direct_deps)
            for prereq in direct_deps:
                if _path_exists_excluding_direct(
                    graph,
                    start=dependent_id,
                    goal=prereq,
                    excluded_first_hop=prereq,
                ):
                    node = graph.nodes.get(dependent_id)
                    out.append(Diagnostic(
                        level="info",
                        node_id=dependent_id,
                        message=(
                            f"direct dependency on {prereq!r} is redundant; "
                            f"{dependent_id!r} already reaches it transitively"
                        ),
                        file_path=node.file_path if node is not None else None,
                        code=self.code,
                        related=(prereq,),
                    ))
        return out


def _path_exists_excluding_direct(
    graph: KnowledgeGraph,
    *,
    start: str,
    goal: str,
    excluded_first_hop: str,
) -> bool:
    """Return True iff there is a path start -> ... -> goal in the `uses` graph
    that does not begin with the direct edge start -> excluded_first_hop.

    The `uses` graph stores ``edges[u]`` as the prerequisites of ``u``.
    BFS therefore walks toward the start node's transitive prerequisites.
    """
    seen: set[str] = {start}
    queue: deque[str] = deque()
    for neighbor in graph.edges.get(start, ()):
        if neighbor == excluded_first_hop:
            continue
        if neighbor == goal:
            return True
        if neighbor not in seen:
            seen.add(neighbor)
            queue.append(neighbor)
    while queue:
        current = queue.popleft()
        for neighbor in graph.edges.get(current, ()):
            if neighbor == goal:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False
```

#### Step 1.3: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_structure.py::TestRedundantDepDetector -q`
- [ ] Expected: all five tests pass.

#### Step 1.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: 580 + 5 = 585 passing.

#### Step 1.5: Commit Task 1

```bash
git add tools/knowledge/lint.py tests/test_lint_structure.py
git commit -m "$(cat <<'EOF'
feat(lint): add RedundantDepDetector (LINT_REDUNDANT_DEP)

For each direct uses edge u -> v, BFS from u over edges other than
u -> v; if v is still reachable transitively, the direct edge is
redundant. Emits an info-level diagnostic that names both endpoints
and stores the redundant prerequisite in `related`. Pure stdlib;
no new dependencies. Issue #121, PR 4.
EOF
)"
```

---

### Task 2: `OrphanDetector`

**Files:**
- Modify: `tools/knowledge/lint.py`
- Modify: `tests/test_lint_structure.py`

#### Step 2.1: Write the first failing tests

Append to `tests/test_lint_structure.py`:

```python
class TestOrphanDetector:
    def test_isolated_node_is_orphan(self):
        a = _node("topic.solo", kind="definition")
        graph, _ = build_graph([a])
        out = OrphanDetector().run([a], graph, llm=None)
        assert len(out) == 1
        d = out[0]
        assert d.level == "info"
        assert d.code == "LINT_ORPHAN"
        assert d.node_id == "topic.solo"
        assert d.related == ()

    def test_node_with_outgoing_dep_is_not_orphan(self):
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        out = OrphanDetector().run([a, b], graph, llm=None)
        ids = {d.node_id for d in out}
        # b has out-deg 1; a has in-deg 1. Neither is orphan.
        assert ids == set()

    def test_node_with_incoming_dep_is_not_orphan(self):
        # Same fixture as above, but assert from the receiving side explicitly.
        a = _node("topic.a", kind="definition")
        b = _node("topic.b", uses=["topic.a"])
        graph, _ = build_graph([a, b])
        out = OrphanDetector().run([a, b], graph, llm=None)
        assert all(d.node_id != "topic.a" for d in out)

    def test_multiple_orphans(self):
        a = _node("topic.solo_one", kind="definition")
        b = _node("topic.solo_two", kind="definition")
        c = _node("topic.c", kind="definition")
        d = _node("topic.d", uses=["topic.c"])
        graph, _ = build_graph([a, b, c, d])
        out = OrphanDetector().run([a, b, c, d], graph, llm=None)
        ids = {x.node_id for x in out}
        # solo_one and solo_two are orphans; c and d form a chain.
        assert ids == {"topic.solo_one", "topic.solo_two"}

    def test_proof_plan_with_target_but_no_uses_is_not_orphan(self):
        # Proof plans attach to their targets through proof_plan_targets,
        # not through uses. They should not be flagged as orphans just
        # because their uses list is empty.
        thm = _node("topic.thm", kind="theorem")
        plan = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
        )
        graph, diags = build_graph([thm, plan])
        assert diags == []
        out = OrphanDetector().run([thm, plan], graph, llm=None)
        ids = {x.node_id for x in out}
        # thm has the plan attached; plan has a target. Neither is orphan.
        assert "topic.thm.plan.direct" not in ids
        assert "topic.thm" not in ids
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_structure.py::TestOrphanDetector -q`
- [ ] Expected: `ImportError: cannot import name 'OrphanDetector'`.

#### Step 2.2: Implement the detector

Append to `tools/knowledge/lint.py` (right after `RedundantDepDetector`):

```python
@dataclass
class OrphanDetector:
    """Flag nodes with no incoming `uses` edges and no outgoing `uses` edges.

    Proof-plan attachments (target / proof_plan_targets / proof_plans_by_target)
    are intentionally considered non-orphan even when uses is empty: a plan
    attached to a theorem is not stranded, and a theorem with at least one
    candidate plan is being actively reasoned about.
    """

    code: str = "LINT_ORPHAN"
    needs_llm: bool = False

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
            if graph.edges.get(node_id):
                continue  # has out-degree
            if graph.reverse_edges.get(node_id):
                continue  # has in-degree
            if node_id in graph.proof_plan_targets:
                continue  # is a plan attached to some target
            if graph.proof_plans_by_target.get(node_id):
                continue  # is a target carrying at least one plan
            out.append(Diagnostic(
                level="info",
                node_id=node_id,
                message=f"node {node_id!r} has no incoming or outgoing dependencies",
                file_path=node.file_path,
                code=self.code,
            ))
        return out
```

#### Step 2.3: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_structure.py::TestOrphanDetector -q`
- [ ] Expected: all five tests pass.

#### Step 2.4: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: 585 + 5 = 590 passing.

#### Step 2.5: Commit Task 2

```bash
git add tools/knowledge/lint.py tests/test_lint_structure.py
git commit -m "$(cat <<'EOF'
feat(lint): add OrphanDetector (LINT_ORPHAN)

Emits info for any node with zero in-degree and zero out-degree in
the uses graph. Excludes proof-plans (which attach via target) and
theorems that carry at least one attached plan. No exception list
for genuine orphans this PR; the design space for an exception
mechanism is tracked in #121 Open Question #1. Issue #121, PR 4.
EOF
)"
```

---

### Task 3: Wire detectors into `_default_detectors()` and verify smoke

**Files:**
- Modify: `tools/knowledge/lint.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 3.1: Write the first failing test

Update the `TestDefaultDetectorsWiring` assertions in `tests/test_lint_orchestrator.py` to expect the new codes:

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
        # PR 3 contributors:
        assert "LINT_FUZZY_DUP" in codes
        assert "LINT_STAGED_OVERLAP" in codes
        # PR 4 contributors:
        assert "LINT_REDUNDANT_DEP" in codes
        assert "LINT_ORPHAN" in codes

        fuzzy = next(d for d in detectors if isinstance(d, FuzzyTitleDupDetector))
        overlap = next(d for d in detectors if isinstance(d, StagedAdmittedOverlapDetector))
        assert fuzzy.threshold == 0.77
        assert overlap.threshold == 0.77
```

The `test_main_runs_default_detectors_against_bundled_example` test from PR 3 should keep passing without changes (the bundled example should remain clean under the new detectors).

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring -q`
- [ ] Expected: assertion failures on the two new code names (the new detectors are not yet in `_default_detectors`).

#### Step 3.2: Update `_default_detectors`

```python
def _default_detectors(config: "LintConfig | None" = None) -> list[Detector]:
    """Return the built-in detector list."""
    from tools.knowledge.config import LintConfig as _LintConfig
    cfg = config if config is not None else _LintConfig()
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
    ]
```

#### Step 3.3: Run orchestrator + full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_orchestrator.py -q`
- [ ] Expected: all orchestrator tests pass.
- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: full suite green.

#### Step 3.4: Smoke against the bundled example

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected: `✅ No lint findings.` and exit 0.

If the bundled example surfaces structural findings (most likely a few `LINT_ORPHAN` results for nodes intentionally kept around as standalone topic anchors), DO NOT change the detector logic to silence them. The acceptance bar here is "deterministic structural tests" — the example may legitimately need either an exception list (deferred to Open Question #1) or a cleanup commit removing genuinely-stranded nodes. Capture the finding list in your final report and proceed — do not commit code changes to make the smoke pass artificially.

If the bundled example surfaces redundant-dep findings, those are likely real bugs in the example. Same handling: capture and report, do not silence.

#### Step 3.5: Confirm `mdblueprint-check` output unchanged

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output.

#### Step 3.6: Commit Task 3

```bash
git add tools/knowledge/lint.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): include RedundantDepDetector and OrphanDetector in defaults

_default_detectors(config) now also returns RedundantDepDetector and
OrphanDetector. Bundled example continues to lint cleanly.
Issue #121, PR 4.
EOF
)"
```

---

## Definition of Done

- [ ] `tools/knowledge/lint.py` defines `RedundantDepDetector` and `OrphanDetector`; both expose `code`, `needs_llm = False`, and `run(...) -> list[Diagnostic]`.
- [ ] `_default_detectors(config)` includes both new detectors in addition to the PR 3 detectors.
- [ ] `tests/test_lint_structure.py` covers redundant chain, no-redundancy chain, parallel deps, diamond, and orphan / non-orphan / proof-plan-attached cases.
- [ ] `tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring` asserts on the four-code set.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0 with no findings at default settings (or, if findings appear, they are captured and reported, NOT silenced by code changes).
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` byte-identical before and after.
- [ ] Three commits on `main` (or feature branch), no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint.py` is under 400 lines (target ~390). If it overshoots, stop and flag for the split called out in the parent plan's Risk Notes.

## Hand-off to PR 5

PR 5 (LeanRefKindDetector) introduces the first detector that needs an external artifact (`LeanIndex`). It does not need LLM yet; that's PR 6+. The pattern stays the same: a new dataclass detector in `tools/knowledge/lint.py`, appended to `_default_detectors(config)`, with an info-level "skipped — no Lean index" diagnostic when the project has no Lean root configured.
