# Blueprint Lint PR 5 — Detector 6 (Lean ref kind mismatch) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `LeanRefKindDetector` (code `LINT_LEAN_KIND`) — for every node that lists Lean declarations in `lean.declarations`, resolve each declaration against the corresponding Lean repository index and compare the declared Lean kind (`def`, `theorem`, `lemma`, …) against the kind class implied by the node's mdblueprint kind. Mismatches surface as warnings. When no Lean repository is configured (or the configured index has zero declarations), the detector emits a single `info` diagnostic and returns without warnings.

**Architecture:** The detector accepts an injected `dict[str, LeanIndex] | None` so tests can drive it with hand-built indexes and `main()` can build them once from `config.lean` rather than each detector re-indexing the project. `_default_detectors(config, lean_indexes=...)` grows the keyword arg; `main()` indexes the configured Lean repositories (reusing the same helper `tools/knowledge/renderer.py` already uses) and threads them through. The detector itself lives in `tools/knowledge/lint/_detectors.py`.

**Tech Stack:** Python 3.10+, stdlib (`dataclasses`, `typing`), pytest. No new dependencies. Uses existing `tools.knowledge.lean_index.LeanIndex`/`LeanDeclaration` and the `_matching_declarations` resolution logic already in `tools.knowledge.lean_check`.

**Parent plan:** [2026-05-23-blueprint-lint.md](2026-05-23-blueprint-lint.md) (PR 5 row).

**Tracking issue:** [#121](https://github.com/gametheoryinlean/mdblueprint/issues/121).

---

## Context

PR 1-4 (Diagnostic, Linter, fuzzy/overlap, redundant/orphan) are on `main`. After PR 4 plus the post-PR 4 split, the lint package is:

```
tools/knowledge/lint/
    __init__.py     # public re-exports
    _core.py        # Detector protocol, Linter, renderers, CLI, _default_detectors, main
    _detectors.py   # the four detector dataclasses + their helpers
```

Real APIs the new detector uses (do not reimplement):

- `tools.knowledge.lean_index.LeanIndex` — `declarations: dict[str, LeanDeclaration]` keyed by **qualified name**; built by `index_lean_project(lean_root, *, repository=None)`.
- `tools.knowledge.lean_index.LeanDeclaration` — `kind: str` is one of `def`, `theorem`, `lemma`, `abbrev`, `instance`, `structure`, `class`, `inductive` (per `_CANONICAL_KIND` in `lean_index.py`).
- `tools.knowledge.config.LeanRepositoryConfig` — `local_path: Path` is where the indexer reads from.
- `tools.knowledge.models.Node.lean: LeanRef | None` — when present, `lean.repository: str | None` selects which configured repo to resolve against (`None` ⇒ default repository).

The match logic for `decl` in `node.lean.declarations` against `LeanIndex.declarations` mirrors `tools.knowledge.lean_check._matching_declarations`: an exact key match wins; otherwise look for declarations whose qualified name ends with `.<decl>` (suffix match for unqualified entries). We can either import the helper or copy a small inlined version — the latter keeps `_detectors.py` self-contained.

### Kind mapping

The lint detector compares the resolved `LeanDeclaration.kind` against the **expected Lean-side kind class** for the node:

| Node kind | Expected Lean kinds |
|---|---|
| `definition`, `concept` | `def`, `abbrev`, `structure`, `class`, `inductive`, `instance` |
| `lemma`, `proposition`, `theorem`, `external-theorem` | `theorem`, `lemma` |
| Anything else (topic, example, proof-plan, task) | The detector skips — these don't carry first-class Lean statement obligations even when `lean.declarations` is set. |

A mismatch is for example: node `kind: theorem` resolving to a Lean `def`, or node `kind: definition` resolving to a Lean `theorem`. Both cases indicate the author wired the wrong Lean entity into the node frontmatter.

## File Structure

- **Create**: none.
- **Modify**: `tools/knowledge/lint/_detectors.py` — append `LeanRefKindDetector` and a private `_lean_kind_classes` mapping.
- **Modify**: `tools/knowledge/lint/_core.py` — `_default_detectors(config, *, lean_indexes=None)` signature; `main()` builds `lean_indexes` from the project config and threads them.
- **Modify**: `tools/knowledge/lint/__init__.py` — re-export `LeanRefKindDetector`.
- **Create**: `tests/test_lint_lean_kind.py` — TDD coverage with hand-built `LeanIndex` fixtures.
- **Modify**: `tests/test_lint_orchestrator.py` — `TestDefaultDetectorsWiring` adds `LINT_LEAN_KIND` to the expected code set; updates the `_default_detectors` call site if it passes a config-only positional.

After PR 5, `tools/knowledge/lint/_detectors.py` is projected at ~360 lines (under the 400-line per-file threshold).

---

### Task 1: `LeanRefKindDetector` core

**Files:**
- Modify: `tools/knowledge/lint/_detectors.py`
- Create: `tests/test_lint_lean_kind.py`

#### Step 1.1: Write the first failing tests

- [ ] Create `tests/test_lint_lean_kind.py`:

```python
"""Tests for LeanRefKindDetector (PR 5)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.knowledge.graph import build_graph
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex
from tools.knowledge.lint import LeanRefKindDetector
from tools.knowledge.models import LeanRef, Node


def _decl(qualified_name: str, kind: str, *, has_sorry: bool = False) -> LeanDeclaration:
    return LeanDeclaration(
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        kind=kind,
        file=Path(f"{qualified_name.replace('.', '/')}.lean"),
        line=1,
        has_sorry=has_sorry,
    )


def _index(decls: list[LeanDeclaration]) -> LeanIndex:
    idx = LeanIndex()
    for d in decls:
        idx.declarations[d.qualified_name] = d
    return idx


def _node(node_id: str, *, kind: str, status: str = "formalized", lean_decls: list[str] | None = None) -> Node:
    return Node(
        id=node_id,
        title=node_id,
        kind=kind,
        status=status,
        lean=LeanRef(modules=["Lib.Mod"], declarations=list(lean_decls or [])),
    )


class TestKindMatching:
    def test_theorem_matched_by_lean_theorem_is_silent(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "theorem")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_theorem_with_lean_def_is_a_warning(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.thing"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.thing", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "warning"
        assert d.code == "LINT_LEAN_KIND"
        assert d.node_id == "topic.thm"
        assert d.related == ("Lib.thing",)
        assert "theorem" in d.message
        assert "def" in d.message

    def test_definition_matched_by_lean_structure_is_silent(self):
        node = _node("topic.def", kind="definition", lean_decls=["Lib.Group"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.Group", "structure")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_definition_with_lean_theorem_is_a_warning(self):
        node = _node("topic.def", kind="definition", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "theorem")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].code == "LINT_LEAN_KIND"
        assert diags[0].related == ("Lib.proof_x",)

    def test_concept_matches_definition_class(self):
        # `concept` shares the definition kind class.
        node = _node("topic.cpt", kind="concept", lean_decls=["Lib.MyClass"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.MyClass", "class")])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_lemma_proposition_external_theorem_all_in_theorem_class(self):
        nodes = [
            _node("topic.lem", kind="lemma", lean_decls=["Lib.x"]),
            _node("topic.prop", kind="proposition", lean_decls=["Lib.y"]),
            _node("topic.ext", kind="external-theorem", lean_decls=["Lib.z"]),
        ]
        graph, _ = build_graph(nodes)
        indexes = {"default": _index([
            _decl("Lib.x", "theorem"),
            _decl("Lib.y", "lemma"),
            _decl("Lib.z", "theorem"),
        ])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run(nodes, graph, llm=None) == []


class TestUnresolvedReferences:
    def test_declaration_missing_from_index_is_skipped_silently(self):
        # Reference resolution failures are check.py's job (lean_check.py
        # already reports them). The lint detector only speaks about kind
        # mismatches and stays silent when there's nothing to compare.
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.does_not_exist"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []


class TestSuffixMatching:
    def test_unqualified_decl_resolves_against_suffix(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.Mod.proof_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        # Even though the declaration was listed unqualified, the kind
        # mismatch is still reported once the suffix match resolves.
        assert len(diags) == 1
        assert diags[0].code == "LINT_LEAN_KIND"

    def test_ambiguous_suffix_match_skips_silently(self):
        # If a short name matches multiple qualified entries, kind comparison
        # is ambiguous; defer to check.py (which reports the ambiguity) and
        # keep the lint detector quiet.
        node = _node("topic.thm", kind="theorem", lean_decls=["proof_x"])
        graph, _ = build_graph([node])
        indexes = {"default": _index([
            _decl("Lib.A.proof_x", "def"),
            _decl("Lib.B.proof_x", "theorem"),
        ])}
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []


class TestRepositoryRouting:
    def test_node_with_explicit_repository_uses_that_index(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        node.lean.repository = "external"
        graph, _ = build_graph([node])
        indexes = {
            "default": _index([_decl("Lib.proof_x", "def")]),     # would mismatch
            "external": _index([_decl("Lib.proof_x", "theorem")]),  # matches
        }
        det = LeanRefKindDetector(indexes=indexes)
        assert det.run([node], graph, llm=None) == []

    def test_node_without_repository_uses_default(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        node.lean.repository = None
        graph, _ = build_graph([node])
        indexes = {"default": _index([_decl("Lib.proof_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1


class TestNonMathKindsAreSkipped:
    def test_proof_plan_kind_is_skipped(self):
        node = Node(
            id="topic.thm.plan.direct",
            title="Plan",
            kind="proof-plan",
            status="staged",
            target="topic.thm",
            plan_status="candidate",
            lean=LeanRef(modules=[], declarations=["Lib.plan_x"]),
        )
        thm = _node("topic.thm", kind="theorem")
        graph, _ = build_graph([thm, node])
        indexes = {"default": _index([_decl("Lib.plan_x", "def")])}
        det = LeanRefKindDetector(indexes=indexes)
        # Proof plans don't carry first-class Lean statement obligations; skip them.
        assert det.run([thm, node], graph, llm=None) == []


class TestNoLeanIndexAvailable:
    def test_none_indexes_emit_single_info(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        det = LeanRefKindDetector(indexes=None)
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        d = diags[0]
        assert d.level == "info"
        assert d.code == "LINT_LEAN_KIND"
        assert "lean index not available" in d.message.lower()

    def test_empty_indexes_dict_emit_single_info(self):
        node = _node("topic.thm", kind="theorem", lean_decls=["Lib.proof_x"])
        graph, _ = build_graph([node])
        det = LeanRefKindDetector(indexes={})
        diags = det.run([node], graph, llm=None)
        assert len(diags) == 1
        assert diags[0].level == "info"
        assert "lean index not available" in diags[0].message.lower()
```

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_lean_kind.py -q`
- [ ] Expected: `ImportError: cannot import name 'LeanRefKindDetector'`.

#### Step 1.2: Implement the detector

Append to `tools/knowledge/lint/_detectors.py` (after `OrphanDetector`):

```python
from tools.knowledge.lean_index import LeanDeclaration, LeanIndex


_LEAN_KINDS_FOR_DEFINITION = frozenset({"def", "abbrev", "structure", "class", "inductive", "instance"})
_LEAN_KINDS_FOR_THEOREM = frozenset({"theorem", "lemma"})

_LEAN_KIND_CLASSES: dict[str, frozenset[str]] = {
    "definition": _LEAN_KINDS_FOR_DEFINITION,
    "concept": _LEAN_KINDS_FOR_DEFINITION,
    "lemma": _LEAN_KINDS_FOR_THEOREM,
    "proposition": _LEAN_KINDS_FOR_THEOREM,
    "theorem": _LEAN_KINDS_FOR_THEOREM,
    "external-theorem": _LEAN_KINDS_FOR_THEOREM,
}


def _resolve_declaration(decl: str, index: LeanIndex) -> LeanDeclaration | None:
    """Resolve a (possibly unqualified) declaration name against an index.

    Mirrors tools.knowledge.lean_check._matching_declarations: prefer an
    exact qualified-name hit; fall back to suffix matches ending in `.<decl>`.
    Returns None when the lookup is ambiguous or has no match — both cases
    are handled elsewhere (check.py reports ambiguity / missing names).
    """
    exact = index.declarations.get(decl)
    if exact is not None:
        return exact
    suffix = f".{decl}"
    matches = [d for qn, d in index.declarations.items() if qn.endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    return None


@dataclass
class LeanRefKindDetector:
    """Flag nodes whose Lean declaration kind contradicts the node's mdblueprint kind."""

    indexes: dict[str, LeanIndex] | None = None
    code: str = "LINT_LEAN_KIND"
    needs_llm: bool = False

    def run(
        self,
        nodes: list[Node],
        graph: KnowledgeGraph,
        *,
        llm: LlmRunner | None,
    ) -> list[Diagnostic]:
        if not self.indexes:
            return [Diagnostic(
                level="info",
                node_id="",
                message="lean index not available; skipping LINT_LEAN_KIND",
                code=self.code,
            )]

        default_index = self.indexes.get("default") or next(iter(self.indexes.values()), None)
        out: list[Diagnostic] = []
        for node_id in sorted(graph.nodes):
            node = graph.nodes[node_id]
            expected = _LEAN_KIND_CLASSES.get(node.kind)
            if expected is None:
                continue
            if node.lean is None or not node.lean.declarations:
                continue

            repo_id = node.lean.repository
            index = self.indexes.get(repo_id) if repo_id is not None else default_index
            if index is None:
                continue

            for decl_name in node.lean.declarations:
                resolved = _resolve_declaration(decl_name, index)
                if resolved is None:
                    continue
                if resolved.kind not in expected:
                    out.append(Diagnostic(
                        level="warning",
                        node_id=node.id,
                        message=(
                            f"node kind {node.kind!r} expects a Lean "
                            f"{'/'.join(sorted(expected))} declaration; "
                            f"{decl_name!r} is a Lean {resolved.kind!r}"
                        ),
                        file_path=node.file_path,
                        code=self.code,
                        related=(decl_name,),
                    ))
        return out
```

#### Step 1.3: Re-export from the package

- [ ] Add `LeanRefKindDetector` to the `from tools.knowledge.lint._detectors import ...` line in `tools/knowledge/lint/__init__.py`, and add it to `__all__`.

#### Step 1.4: Run the new tests

- [ ] Run: `uv run --extra dev python -m pytest tests/test_lint_lean_kind.py -q`
- [ ] Expected: every test (kind match, mismatch, repository routing, unresolved, ambiguity, non-math skip, no-index) passes.

#### Step 1.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: 590 + 13 = 603 passing.

#### Step 1.6: Commit Task 1

```bash
git add tools/knowledge/lint/_detectors.py tools/knowledge/lint/__init__.py tests/test_lint_lean_kind.py
git commit -m "$(cat <<'EOF'
feat(lint): add LeanRefKindDetector (LINT_LEAN_KIND)

For each node whose mdblueprint kind has an expected Lean-side
kind class (definition/concept -> def/abbrev/structure/class/
inductive/instance; lemma/proposition/theorem/external-theorem ->
theorem/lemma), resolve each entry in node.lean.declarations
against the injected LeanIndex and warn on mismatches. Resolution
mirrors lean_check._matching_declarations (exact, then unique
suffix). When the indexes mapping is empty or None, emit a single
info diagnostic and return — missing Lean root is not a lint
failure, it's a tooling availability signal.

Detector is injection-driven so tests pass hand-built indexes;
PR 5 Task 2 wires real-index construction into _default_detectors
and main(). Issue #121, PR 5.
EOF
)"
```

---

### Task 2: Wire `LeanRefKindDetector` into `_default_detectors` and `main`

**Files:**
- Modify: `tools/knowledge/lint/_core.py`
- Modify: `tests/test_lint_orchestrator.py`

#### Step 2.1: Update the `TestDefaultDetectorsWiring` expectations

In `tests/test_lint_orchestrator.py`, expand the `_default_detectors` wiring test:

```python
class TestDefaultDetectorsWiring:
    def test_default_detectors_use_threshold_from_config(self, tmp_path: Path):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lint import (
            FuzzyTitleDupDetector,
            LeanRefKindDetector,
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
        # PR 5 contributor:
        assert "LINT_LEAN_KIND" in codes

        fuzzy = next(d for d in detectors if isinstance(d, FuzzyTitleDupDetector))
        overlap = next(d for d in detectors if isinstance(d, StagedAdmittedOverlapDetector))
        assert fuzzy.threshold == 0.77
        assert overlap.threshold == 0.77

        lean_kind = next(d for d in detectors if isinstance(d, LeanRefKindDetector))
        # Without explicit lean_indexes, the detector is constructed in
        # "no index available" mode and produces a single info diagnostic
        # rather than warnings.
        assert lean_kind.indexes is None

    def test_default_detectors_accept_lean_indexes_kwarg(self):
        from tools.knowledge.config import LintConfig
        from tools.knowledge.lean_index import LeanIndex
        from tools.knowledge.lint import LeanRefKindDetector, _default_detectors

        indexes = {"default": LeanIndex()}
        detectors = _default_detectors(LintConfig(), lean_indexes=indexes)
        lean_kind = next(d for d in detectors if isinstance(d, LeanRefKindDetector))
        assert lean_kind.indexes is indexes
```

#### Step 2.2: Update `_default_detectors` signature

In `tools/knowledge/lint/_core.py`:

```python
def _default_detectors(
    config: "LintConfig | None" = None,
    *,
    lean_indexes: "dict[str, LeanIndex] | None" = None,
) -> list[Detector]:
    """Return the built-in detector list."""
    from tools.knowledge.config import LintConfig as _LintConfig
    cfg = config if config is not None else _LintConfig()
    return [
        FuzzyTitleDupDetector(threshold=cfg.fuzzy_threshold),
        StagedAdmittedOverlapDetector(threshold=cfg.fuzzy_threshold),
        RedundantDepDetector(),
        OrphanDetector(),
        LeanRefKindDetector(indexes=lean_indexes),
    ]
```

Add the `LeanRefKindDetector` import and the `if TYPE_CHECKING` `LeanIndex` import as needed to keep `_core.py` quiet at module load time. Note `LeanIndex` only needs to be importable at type-check time; the actual runtime use is in `main()`.

#### Step 2.3: Update `main()` to build real Lean indexes

```python
def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    from tools.knowledge.config import load_project_config
    from tools.knowledge.lean_index import index_lean_project

    config = load_project_config(args.knowledge_root)
    lean_indexes: dict[str, "LeanIndex"] = {}
    for repo_id, repo in config.lean.repositories.items():
        if repo.local_path.exists():
            try:
                lean_indexes[repo_id] = index_lean_project(repo.local_path, repository=repo)
            except Exception:
                # Indexing failures are not lint errors — they belong to
                # `mdblueprint-check`. Skip the repo silently here; the
                # LeanRefKindDetector falls back to "no index" behavior
                # when none of the configured repos resolved.
                continue
    if config.lean.default_repository and config.lean.default_repository in lean_indexes:
        # Alias the chosen default under the literal "default" key so the
        # detector's lookup `indexes.get("default") or next(...)` finds it
        # for nodes whose lean.repository is unset.
        lean_indexes.setdefault("default", lean_indexes[config.lean.default_repository])

    llm: LlmRunner | None = None
    if args.llm:
        llm = _make_claude_cli_runner(model=args.model)
    linter = Linter(
        detectors=_default_detectors(config.lint, lean_indexes=lean_indexes or None),
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

#### Step 2.4: Smoke against the bundled example

- [ ] Run: `uv run mdblueprint-lint docs/knowledge`
- [ ] Expected:
  - Continues to surface the two existing `LINT_REDUNDANT_DEP` findings from PR 4.
  - Adds one `LINT_LEAN_KIND` info "lean index not available; skipping LINT_LEAN_KIND" diagnostic (since `docs/knowledge` has no Lean root configured by default).
  - Exit code 0 (info-level only).

#### Step 2.5: Run the full suite

- [ ] Run: `uv run --extra dev python -m pytest tests/ -q --ignore=tests/test_serve_integration.py`
- [ ] Expected: all tests pass (603 + 2 wiring = 605).

#### Step 2.6: Confirm `mdblueprint-check` output unchanged

```bash
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-after.txt 2>&1 || true
git stash -u
uv run python -m tools.knowledge.check docs/knowledge > /tmp/check-before.txt 2>&1 || true
git stash pop
diff -u /tmp/check-before.txt /tmp/check-after.txt
```

- [ ] Expected: `diff` exits 0 with no output.

#### Step 2.7: Commit Task 2

```bash
git add tools/knowledge/lint/_core.py tests/test_lint_orchestrator.py
git commit -m "$(cat <<'EOF'
feat(lint): wire LeanRefKindDetector into _default_detectors + CLI

main() now builds a LeanIndex per configured repository (silently
skipping repos that fail to index — that's check.py's job) and
threads the dict into _default_detectors via the new lean_indexes
keyword arg. Nodes whose lean.repository is unset resolve through
an alias entry under the "default" key, set from
config.lean.default_repository. When no repository is configured
(common for the bundled example), the detector falls back to the
info-level "lean index not available" diagnostic established in
Task 1. Issue #121, PR 5.
EOF
)"
```

---

## Definition of Done

- [ ] `tools/knowledge/lint/_detectors.py` defines `LeanRefKindDetector` with `code="LINT_LEAN_KIND"`, `needs_llm=False`, and an injected `indexes: dict[str, LeanIndex] | None`.
- [ ] `_resolve_declaration` mirrors `lean_check._matching_declarations` (exact then unique suffix).
- [ ] `_LEAN_KIND_CLASSES` maps every mdblueprint kind that carries Lean statement obligations to its accepted Lean-kind set; other kinds (`topic`, `example`, `proof-plan`, `task`) are skipped silently.
- [ ] `_default_detectors(config, *, lean_indexes=None)` includes the detector with the passed-in indexes.
- [ ] `main()` builds a real `dict[str, LeanIndex]` from `config.lean.repositories` and threads it through. Indexing exceptions are swallowed (not a lint failure).
- [ ] `tests/test_lint_lean_kind.py` covers: every kind-class match/mismatch pair, suffix matching, ambiguous suffix, explicit repository routing, default repository, non-math-kind skip, and the no-index info path.
- [ ] `tests/test_lint_orchestrator.py::TestDefaultDetectorsWiring` asserts on the five-code set and verifies the `lean_indexes` kwarg flows through.
- [ ] `uv run mdblueprint-lint docs/knowledge` exits 0; output now includes one `LINT_LEAN_KIND` info plus the two pre-existing `LINT_REDUNDANT_DEP` infos.
- [ ] `uv run python -m tools.knowledge.check docs/knowledge` byte-identical before and after.
- [ ] Two commits on `main` (or feature branch), no `Co-Authored-By` trailers.
- [ ] `tools/knowledge/lint/_detectors.py` under 400 lines (target ~360).

## Hand-off to PR 6

PR 6 introduces the LLM detector infrastructure: a content-hashed cache, a budget enforcer, the first semantic-judgement detector (`SemanticDupDetector`, code `LINT_SEMANTIC_DUP`). The pattern from PR 5 — constructor-injected dependency, `_default_detectors(config, *, lean_indexes=..., llm_cache_dir=..., budget=...)` — extends naturally.
