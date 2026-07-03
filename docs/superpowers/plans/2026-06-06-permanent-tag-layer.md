# Permanent Tag Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every knowledge node an opaque, permanent, never-reused tag (e.g. `0A7F`) so that taxonomy refactors and node merges never break references — the foundational identity layer for the fif Langlands KB (spec: `../../../../fif/docs/superpowers/specs/2026-06-06-fif-langlands-design.md`, schema delta ①).

**Architecture:** Additive and non-breaking. This plan introduces the `tag` field, its format/uniqueness validation, a deterministic stateless minting tool, and a one-time migration of the existing knowledge base. It does **not** yet switch `uses` / `[[node:id]]` references from id to tag — that is a later plan once tags exist everywhere. Tags are minted as zero-padded base-36 of `(max existing tag value) + 1`, so minting needs no persisted counter and never collides.

**Tech Stack:** Python 3.10+, dataclasses, PyYAML, pytest, `uv`. New module `tools/knowledge/tags.py`; new CLI `mdblueprint-mint-tags`.

---

## File Structure

- **Create** `tools/knowledge/tags.py` — pure tag codec + minting logic (`encode_tag`, `decode_tag`, `TAG_RE`, `next_free_tags`, `insert_tag_line`, `has_tag_line`). One responsibility: tag arithmetic and frontmatter text surgery. No graph/validation knowledge.
- **Create** `tools/knowledge/mint_tags.py` — CLI wrapper doing file IO over a knowledge root; depends on `tags.py`.
- **Create** `tests/test_tags.py` — unit tests for the codec/minting module.
- **Modify** `tools/knowledge/models.py` — add `tag` field to `Node`.
- **Modify** `tools/knowledge/parser.py` — read `tag` from frontmatter.
- **Modify** `tools/knowledge/validator.py` — tag format check + admitted-missing-tag warning.
- **Modify** `tools/knowledge/graph.py` — tag uniqueness check in `build_graph`.
- **Modify** `tests/test_parser.py`, `tests/test_validator.py`, `tests/test_graph.py` — coverage for the above.
- **Modify** `pyproject.toml` — register `mdblueprint-mint-tags` script.
- **Modify** `docs/node-format.md` — document the `tag` field.
- **Migrate** every `*.md` under `docs/knowledge/nodes/` and `docs/knowledge/staged/` — add a minted `tag`.

---

## Task 1: Add `tag` field to the node model and parser

**Files:**
- Modify: `tools/knowledge/models.py` (Node dataclass, after `id`)
- Modify: `tools/knowledge/parser.py` (`parse_node`, the `Node(...)` construction)
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_parser.py`:

```python
def test_parses_tag_field():
    text = (
        "---\n"
        "id: topology.metric_space.complete\n"
        "tag: 0A7F\n"
        "title: Complete Metric Space\n"
        "kind: definition\n"
        "status: admitted\n"
        "---\n"
        "Body.\n"
    )
    node = parse_node(text)
    assert node.tag == "0A7F"


def test_tag_absent_is_none():
    text = (
        "---\n"
        "id: x.y\n"
        "title: T\n"
        "kind: definition\n"
        "status: admitted\n"
        "---\n"
        "Body.\n"
    )
    node = parse_node(text)
    assert node.tag is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_parser.py::test_parses_tag_field -v`
Expected: FAIL with `AttributeError: 'Node' object has no attribute 'tag'`

- [ ] **Step 3: Add the field to the model**

In `tools/knowledge/models.py`, in the `@dataclass class Node:` block, the first four fields are non-default required fields (`id`, `title`, `kind`, `status`), followed by defaulted fields (`uses`, ...). A defaulted field **must not** precede a non-default field, so add `tag` as the **first defaulted field**, immediately after `status: str` and before `uses:`:

```python
    id: str
    title: str
    kind: str
    status: str
    tag: str | None = None
    uses: list[str] = field(default_factory=list)
```

Note: every construction site uses keyword arguments (`parse_node` and the tests build `Node(id=..., tag=..., title=...)`), so field order does not affect callers — it only needs to satisfy the dataclass default-ordering rule.

- [ ] **Step 4: Read the field in the parser**

In `tools/knowledge/parser.py`, inside `parse_node`, in the `return Node(` call, add right after `id=fm.get("id", ""),`:

```python
        id=fm.get("id", ""),
        tag=fm.get("tag") or None,
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_parser.py -q`
Expected: PASS (including the two new tests)

- [ ] **Step 6: Commit**

```bash
git add tools/knowledge/models.py tools/knowledge/parser.py tests/test_parser.py
git commit -m "feat(tags): add permanent tag field to node model and parser"
```

---

## Task 2: Validate tag format

**Files:**
- Create: `tools/knowledge/tags.py`
- Modify: `tools/knowledge/validator.py` (`validate_node`)
- Test: `tests/test_validator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validator.py`:

```python
class TestTagFormat:
    def _node(self, tag):
        text = (
            "---\n"
            "id: x.y\n"
            f"tag: {tag}\n"
            "title: T\n"
            "kind: definition\n"
            "status: admitted\n"
            "---\n"
            "Body.\n"
        )
        return parse_node(text)

    def test_valid_tag_no_error(self):
        diags = validate_node(self._node("0A7F"), is_staged_dir=False)
        assert not any("tag" in d.message and d.level == "error" for d in diags)

    def test_lowercase_tag_errors(self):
        diags = validate_node(self._node("0a7f"), is_staged_dir=False)
        assert any("tag" in d.message and d.level == "error" for d in diags)

    def test_too_short_tag_errors(self):
        diags = validate_node(self._node("0A7"), is_staged_dir=False)
        assert any("tag" in d.message and d.level == "error" for d in diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_validator.py::TestTagFormat -v`
Expected: FAIL — `test_lowercase_tag_errors` and `test_too_short_tag_errors` fail (no tag error emitted).

- [ ] **Step 3: Create the tags module with the format regex**

Create `tools/knowledge/tags.py`:

```python
"""Permanent node tags: opaque, never-reused identity decoupled from id/slug.

A tag is a fixed-length base-36 string (e.g. ``0A7F``). Tags are minted as the
zero-padded base-36 encoding of ``(max existing tag value) + 1`` so minting is
stateless (no persisted counter) and collision-free across a knowledge root.
"""
from __future__ import annotations

import re

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TAG_LENGTH = 4
TAG_RE = re.compile(r"^[0-9A-Z]{4}$")


def encode_tag(value: int) -> str:
    """Encode a non-negative int as a zero-padded base-36 tag."""
    if value < 0:
        raise ValueError(f"tag value must be non-negative, got {value}")
    n = value
    chars: list[str] = []
    for _ in range(TAG_LENGTH):
        n, r = divmod(n, 36)
        chars.append(ALPHABET[r])
    if n != 0:
        raise ValueError(f"value {value} too large for tag length {TAG_LENGTH}")
    return "".join(reversed(chars))


def decode_tag(tag: str) -> int:
    """Decode a tag back to its integer value."""
    if not TAG_RE.match(tag):
        raise ValueError(f"malformed tag: {tag!r}")
    value = 0
    for ch in tag:
        value = value * 36 + ALPHABET.index(ch)
    return value
```

- [ ] **Step 4: Add the format check to `validate_node`**

In `tools/knowledge/validator.py`:

First add the import near the top with the other `tools.knowledge` imports:

```python
from tools.knowledge.tags import TAG_RE
```

Then, inside `validate_node`, after the required-field checks for `id`/`title`/`kind` (right after the `if not node.kind:` block near line 144), add:

```python
    if node.tag is not None and not TAG_RE.match(node.tag):
        err(f"invalid tag {node.tag!r}; must match {TAG_RE.pattern}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_validator.py::TestTagFormat tests/test_tags.py -q`
Expected: PASS (test_tags.py reports no tests collected yet — that is fine; TestTagFormat passes)

- [ ] **Step 6: Commit**

```bash
git add tools/knowledge/tags.py tools/knowledge/validator.py tests/test_validator.py
git commit -m "feat(tags): validate permanent tag format"
```

---

## Task 3: Warn when an admitted node has no tag

**Files:**
- Modify: `tools/knowledge/validator.py` (`validate_node`)
- Test: `tests/test_validator.py`

Rationale: tag is optional during this additive rollout, but admitted (durable) nodes should carry one. Warning (not error) keeps the build green until migration runs.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validator.py`, inside `class TestTagFormat`:

```python
    def test_admitted_without_tag_warns(self):
        text = (
            "---\n"
            "id: x.y\n"
            "title: T\n"
            "kind: definition\n"
            "status: admitted\n"
            "---\n"
            "Body.\n"
        )
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=False)
        assert any(
            d.level == "warning" and "tag" in d.message for d in diags
        )

    def test_staged_without_tag_no_warning(self):
        text = (
            "---\n"
            "id: x.y\n"
            "title: T\n"
            "kind: definition\n"
            "status: staged\n"
            "---\n"
            "Body.\n"
        )
        node = parse_node(text)
        diags = validate_node(node, is_staged_dir=True)
        assert not any(
            d.level == "warning" and "tag" in d.message for d in diags
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_validator.py::TestTagFormat::test_admitted_without_tag_warns -v`
Expected: FAIL — no warning emitted.

- [ ] **Step 3: Add the warning**

In `tools/knowledge/validator.py`, immediately after the tag-format check added in Task 2, add:

```python
    if node.tag is None and node.status in ADMITTED_STATUSES:
        warn("admitted node has no permanent tag; run mdblueprint-mint-tags")
```

Ensure `ADMITTED_STATUSES` is imported in `validator.py` from `tools.knowledge.models`. Check the existing model imports at the top of the file; if `ADMITTED_STATUSES` is not among them, add it to that import list.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_validator.py::TestTagFormat -q`
Expected: PASS

- [ ] **Step 5: Verify existing admitted nodes now warn (expected, pre-migration)**

Run: `uv run python -m tools.knowledge.check docs/knowledge`
Expected: command still exits 0 (warnings do not fail the check); tag warnings appear for the 10 existing admitted nodes. This is expected and resolved by Task 7.

- [ ] **Step 6: Commit**

```bash
git add tools/knowledge/validator.py tests/test_validator.py
git commit -m "feat(tags): warn on admitted node without permanent tag"
```

---

## Task 4: Enforce tag uniqueness in the graph build

**Files:**
- Modify: `tools/knowledge/graph.py` (`build_graph`)
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py` (use the existing import of `build_graph` and `Node`; if the test file builds `Node` directly, mirror that style):

```python
def test_duplicate_tag_is_error():
    from tools.knowledge.models import Node
    from tools.knowledge.graph import build_graph

    a = Node(id="a.one", tag="0A7F", title="A", kind="definition", status="admitted")
    b = Node(id="b.two", tag="0A7F", title="B", kind="definition", status="admitted")
    _graph, diags = build_graph([a, b])
    assert any(
        d.level == "error" and "tag" in d.message and "0A7F" in d.message
        for d in diags
    )


def test_distinct_tags_no_tag_error():
    from tools.knowledge.models import Node
    from tools.knowledge.graph import build_graph

    a = Node(id="a.one", tag="0A7F", title="A", kind="definition", status="admitted")
    b = Node(id="b.two", tag="0A80", title="B", kind="definition", status="admitted")
    _graph, diags = build_graph([a, b])
    assert not any(d.level == "error" and "duplicate tag" in d.message for d in diags)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_graph.py::test_duplicate_tag_is_error -v`
Expected: FAIL — no duplicate-tag diagnostic.

- [ ] **Step 3: Add the uniqueness check**

In `tools/knowledge/graph.py`, inside `build_graph`, locate the existing duplicate-**id** loop (around lines 27-38, where `seen_ids` is populated). Immediately after that loop completes (after all nodes are registered in `g.nodes`), add a separate tag pass:

```python
    seen_tags: dict[str, Node] = {}
    for node in nodes:
        if not node.tag:
            continue
        if node.tag in seen_tags:
            prev = seen_tags[node.tag]
            diags.append(Diagnostic(
                "error", node.id,
                f"duplicate tag {node.tag!r}; also used by {prev.id!r}",
            ))
            continue
        seen_tags[node.tag] = node
```

If `Diagnostic` is not already imported in `graph.py`, add it to the imports from `tools.knowledge.validator` (it is constructed elsewhere in this file, so the import already exists — confirm by reading the top of `graph.py`). The diagnostics list inside `build_graph` is the same `diags` used by the existing id check.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_graph.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/knowledge/graph.py tests/test_graph.py
git commit -m "feat(tags): enforce permanent tag uniqueness in graph build"
```

---

## Task 5: Stateless, collision-free minting logic

**Files:**
- Modify: `tools/knowledge/tags.py`
- Test: `tests/test_tags.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tags.py`:

```python
import pytest

from tools.knowledge.tags import (
    encode_tag,
    decode_tag,
    next_free_tags,
    has_tag_line,
    insert_tag_line,
)


def test_encode_roundtrip():
    for v in [0, 1, 35, 36, 37, 1295, 1296, 99999]:
        assert decode_tag(encode_tag(v)) == v


def test_encode_zero_padding():
    assert encode_tag(0) == "0000"
    assert encode_tag(1) == "0001"
    assert encode_tag(36) == "0010"


def test_next_free_starts_above_max():
    existing = {"0000", "0001", "0010"}  # max value 36
    out = next_free_tags(existing, 2)
    assert out == [encode_tag(37), encode_tag(38)]


def test_next_free_empty_starts_at_zero():
    assert next_free_tags(set(), 1) == ["0000"]


def test_next_free_above_existing_max():
    # minting always starts at (max existing value) + 1
    existing = {"0010", "0011"}  # values 36, 37; max is 37
    out = next_free_tags(existing, 1)
    assert out == ["0012"]  # value 38
    assert out[0] not in existing
    assert decode_tag(out[0]) > max(decode_tag(t) for t in existing)


def test_has_and_insert_tag_line():
    text = "---\nid: x.y\ntitle: T\n---\nbody\n"
    assert has_tag_line(text) is False
    out = insert_tag_line(text, "0A7F")
    assert "tag: 0A7F" in out
    assert has_tag_line(out) is True
    # tag line is placed directly after the id line
    lines = out.split("\n")
    assert lines[lines.index("id: x.y") + 1] == "tag: 0A7F"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_tags.py -v`
Expected: FAIL with `ImportError: cannot import name 'next_free_tags'`

- [ ] **Step 3: Implement the minting helpers**

Append to `tools/knowledge/tags.py`:

```python
def next_free_tags(existing: set[str], count: int) -> list[str]:
    """Return ``count`` new tags, each strictly above the current max and not
    colliding with ``existing``. Stateless: derived from the existing set only."""
    start = max((decode_tag(t) for t in existing), default=-1) + 1
    taken = set(existing)
    out: list[str] = []
    value = start
    while len(out) < count:
        candidate = encode_tag(value)
        if candidate not in taken:
            out.append(candidate)
            taken.add(candidate)
        value += 1
    return out


_ID_LINE_RE = re.compile(r"^id:\s", re.MULTILINE)
_TAG_LINE_RE = re.compile(r"^tag:\s", re.MULTILINE)


def has_tag_line(text: str) -> bool:
    """True if the frontmatter already declares a tag."""
    return _TAG_LINE_RE.search(text) is not None


def insert_tag_line(text: str, tag: str) -> str:
    """Insert ``tag: <tag>`` immediately after the first ``id:`` line."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("id:"):
            lines.insert(i + 1, f"tag: {tag}")
            return "\n".join(lines)
    raise ValueError("no 'id:' line found in frontmatter")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_tags.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/knowledge/tags.py tests/test_tags.py
git commit -m "feat(tags): stateless collision-free tag minting helpers"
```

---

## Task 6: `mdblueprint-mint-tags` CLI

**Files:**
- Create: `tools/knowledge/mint_tags.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/test_tags.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_tags.py`:

```python
def test_mint_over_root(tmp_path):
    from tools.knowledge.mint_tags import mint_root

    nodes = tmp_path / "nodes"
    nodes.mkdir()
    (nodes / "a.md").write_text(
        "---\nid: t.a\ntitle: A\nkind: definition\nstatus: admitted\n---\nbody\n",
        encoding="utf-8",
    )
    # already-tagged file must be left untouched
    (nodes / "b.md").write_text(
        "---\nid: t.b\ntag: 0Z00\ntitle: B\nkind: definition\nstatus: admitted\n---\nbody\n",
        encoding="utf-8",
    )

    minted = mint_root(tmp_path)

    assert minted == {str(nodes / "a.md")}  # only the untagged file got a tag
    a_text = (nodes / "a.md").read_text(encoding="utf-8")
    assert "tag: " in a_text
    # new tag is strictly above the existing max (0Z00)
    from tools.knowledge.tags import has_tag_line, decode_tag
    assert has_tag_line(a_text)
    new_tag = [l for l in a_text.splitlines() if l.startswith("tag: ")][0].split(": ")[1]
    assert decode_tag(new_tag) > decode_tag("0Z00")
    # idempotent: a second run mints nothing
    assert mint_root(tmp_path) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_tags.py::test_mint_over_root -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.knowledge.mint_tags'`

- [ ] **Step 3: Implement the CLI module**

Create `tools/knowledge/mint_tags.py`:

```python
"""CLI: mint permanent tags for nodes that lack one, under a knowledge root."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.knowledge.tags import (
    TAG_RE,
    has_tag_line,
    insert_tag_line,
    next_free_tags,
)


def _iter_node_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for sub in ("nodes", "staged"):
        d = root / sub
        if d.is_dir():
            files.extend(sorted(d.rglob("*.md")))
    if not files:  # allow pointing directly at a directory of .md files
        files = sorted(root.rglob("*.md"))
    return files


def _collect_existing_tags(files: list[Path]) -> set[str]:
    existing: set[str] = set()
    for p in files:
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("tag: "):
                tag = line[len("tag: "):].strip()
                if TAG_RE.match(tag):
                    existing.add(tag)
                break
    return existing


def mint_root(root: Path) -> set[str]:
    """Mint tags for every untagged node file under ``root``.

    Returns the set of file paths (as strings) that were modified. Idempotent.
    """
    files = _iter_node_files(root)
    existing = _collect_existing_tags(files)
    untagged = [p for p in files if not has_tag_line(p.read_text(encoding="utf-8"))]
    new_tags = next_free_tags(existing, len(untagged))
    modified: set[str] = set()
    for path, tag in zip(untagged, new_tags):
        text = path.read_text(encoding="utf-8")
        path.write_text(insert_tag_line(text, tag), encoding="utf-8")
        modified.add(str(path))
    return modified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint permanent node tags.")
    parser.add_argument("root", type=Path, help="knowledge root directory")
    args = parser.parse_args(argv)
    modified = mint_root(args.root)
    for p in sorted(modified):
        print(f"minted tag: {p}")
    print(f"{len(modified)} file(s) tagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Register the CLI script**

In `pyproject.toml`, under `[project.scripts]`, add (keep alphabetical-ish ordering near the other `mdblueprint-*` entries):

```toml
mdblueprint-mint-tags = "tools.knowledge.mint_tags:main"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --extra dev python -m pytest tests/test_tags.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tools/knowledge/mint_tags.py pyproject.toml tests/test_tags.py
git commit -m "feat(tags): add mdblueprint-mint-tags CLI"
```

---

## Task 7: Migrate the existing knowledge base

**Files:**
- Migrate: all `*.md` under `docs/knowledge/nodes/` and `docs/knowledge/staged/`

- [ ] **Step 1: Run the minting CLI over the project knowledge base**

Run: `uv run python -m tools.knowledge.mint_tags docs/knowledge`
Expected: prints `minted tag: ...` for each previously-untagged node (the ~10 admitted nodes plus any staged), then `N file(s) tagged`.

- [ ] **Step 2: Verify every node now has a unique, well-formed tag**

Run: `uv run python -m tools.knowledge.check docs/knowledge`
Expected: exits 0; the "admitted node has no permanent tag" warnings from Task 3 are gone; no "duplicate tag" errors.

- [ ] **Step 3: Confirm tags are present in the files**

Run: `grep -rL "^tag: " docs/knowledge/nodes docs/knowledge/staged --include='*.md'`
Expected: no output (every node file contains a `tag:` line).

- [ ] **Step 4: Run the full test suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS (the `test_all_admitted_nodes_valid` test still passes; nodes now additionally carry tags).

- [ ] **Step 5: Commit**

```bash
git add docs/knowledge
git commit -m "chore(tags): mint permanent tags for existing knowledge base"
```

---

## Task 8: Document the tag field

**Files:**
- Modify: `docs/node-format.md`

- [ ] **Step 1: Add a tag section**

In `docs/node-format.md`, after the `## Example` section and before `## Topic Fields`, add:

```markdown
## Permanent Tag

Every node carries a `tag`: an opaque, fixed-length base-36 identifier (e.g.
`0A7F`) that is **permanent and never reused**. The tag is the durable identity
of a node — independent of its `id`, title, topic, or file location. When a node
is renamed, moved to another topic, or merged, the tag stays constant so
references never break.

- Format: four characters matching `^[0-9A-Z]{4}$`.
- Minted by `mdblueprint-mint-tags <knowledge-root>`, which assigns the next
  free tag above the current maximum (stateless, collision-free).
- `id` and the human-readable slug remain the display/authoring layer; the tag
  is the reference layer. (Switching `uses` and `[[node:id]]` to resolve via tag
  is a later migration; today both still resolve by `id`.)
```

- [ ] **Step 2: Verify docs tests still pass**

Run: `uv run --extra dev python -m pytest tests/test_agent_docs.py tests/test_graph_navigation_docs.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/node-format.md
git commit -m "docs(tags): document the permanent tag field"
```

---

## Done criteria

- Every node under `docs/knowledge/` has a unique, well-formed `tag`.
- `mdblueprint-mint-tags` is idempotent and collision-free.
- Validator flags malformed tags (error) and admitted nodes missing a tag (warning).
- `build_graph` flags duplicate tags (error).
- Full test suite green.
- **Out of scope (next plan):** switching `uses` / `[[node:id]]` resolution to tags; making the id slug formally display-only; tag-aware alias/redirect (schema delta ③).
