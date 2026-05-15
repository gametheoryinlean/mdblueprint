# Leanblueprint-Style Publisher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep Markdown nodes as the source of truth while generating a blueprint website and DAG that visually and behaviorally follow leanblueprint.

**Architecture:** Add a small presentation layer that maps `mdblueprint` nodes into leanblueprint-style theorem/definition cards, DOT graph attributes, and modal payloads. Keep parsing, validation, graph construction, and `graph.json` deterministic in Python; the browser only renders Python-generated data and handles interaction.

**Tech Stack:** Python 3, Jinja2, Python-Markdown, existing `tools.knowledge` modules, browser-side MathJax, browser-side Graphviz rendering via pinned `d3-graphviz`/WASM assets or CDN scripts with SRI.

---

All paths below are relative to `/Users/hoxide/mycodes/mdblueprint`.

## Current State

- `tools/knowledge/parser.py`, `validator.py`, `graph.py`, and `export.py` already parse nodes, validate the DAG, and emit stable `graph.json`.
- `tools/knowledge/publish.py` already writes `index.html`, `graph.html`, topic pages, node pages, and `style.css`.
- Current output is structurally correct but not leanblueprint-like: the index is a table, node pages are plain articles, and the graph is a small Cytoscape breadth-first view.
- The generated knowledge base currently has 11 nodes and 14 dependency edges: 9 definitions, 1 theorem, 1 example; 10 admitted, 1 staged.
- Validation is currently clean with `uv run python -m tools.knowledge.check docs/knowledge`.

## Leanblueprint Style Target

- Definitions render as boxed theorem-style blocks; lemmas/propositions/theorems render as theorem-style statement blocks.
- Node headers show caption, stable label/id, title, status/check indicator, dependency modal, Lean declaration modal, and permalink.
- Dependency graph uses Graphviz/DOT layout, not a force/breadth-first canvas layout.
- Graph shape semantics:
  - `definition` and `concept` -> `box`
  - `lemma`, `proposition`, `theorem`, `external-theorem`, `proof-plan` -> `ellipse`
  - `example` -> rounded note-like box
  - `task` -> component or folder-like box, visually distinct from mathematical nodes
- Graph edge direction must be displayed as `dependency -> dependent`, matching leanblueprint, even though `KnowledgeGraph.edges` stores `node -> dependency`.
- Graph colors encode readiness/formalization state:
  - staged/needs review/blocked -> orange border or muted style
  - admitted with all dependencies admitted/formalized/proved -> blue border (`can_state`)
  - formalized -> green border (`stated`)
  - proved theorem -> green fill (`proved`)
  - proved node with all ancestors proved or definitions/formalized -> dark green fill (`fully_proved`)
  - definitions with formalized/proved status -> light green fill (`defined`)
- Clicking a graph node opens a modal containing the same theorem/definition block and links to the node page and Lean declarations.

## File Structure

- Create `tools/knowledge/blueprint_view.py`
  - Pure presentation helpers for labels, captions, shapes, status colors, readiness flags, DOT escaping, and modal/page view models.
  - No filesystem writes.
- Create `tests/test_blueprint_view.py`
  - Unit tests for status mapping, edge direction, labels, DOT escaping, and ancestor-derived `fully_proved`.
- Modify `tools/knowledge/export.py`
  - Keep `graph.json` backward-compatible.
  - Add optional presentation metadata through a new function, not by changing current `export_graph_json()` behavior.
- Modify `tools/knowledge/publish.py`
  - Build blueprint view models once and pass them into templates.
  - Copy new static JavaScript asset(s).
  - Write `dep_graph_document.html` and preserve `graph.html` as the navigation target or compatibility alias.
- Modify `tools/knowledge/templates/base.html`
  - Change navigation labels and include layout hooks needed by theorem-style pages.
- Modify `tools/knowledge/templates/node.html`
  - Render a single node using leanblueprint-style theorem wrappers.
- Modify `tools/knowledge/templates/index.html`
  - Replace the bare table-first feel with a blueprint overview that still includes a scannable node list.
- Modify `tools/knowledge/templates/topic.html`
  - Render topic-local theorem/definition summaries.
- Modify `tools/knowledge/templates/graph.html`
  - Replace Cytoscape with Graphviz-style dependency graph page.
- Create `tools/knowledge/templates/graph.js`
  - Browser interaction only: render DOT, toggle legend, open/close modals, and focus the selected node.
- Modify `tools/knowledge/templates/style.css`
  - Add leanblueprint-style theorem wrappers, modal styling, graph layout, legend, badges, and responsive rules.
- Modify `tests/test_publish.py`
  - Assert new files/classes/content and compatibility behavior.
- Modify `tests/test_export.py`
  - Assert any new presentation graph export is deterministic and non-breaking.
- Modify `README.md` and `docs/publisher-and-dag.md`
  - Document that the source remains Markdown and the generated site intentionally follows leanblueprint style.

## Design Decisions

- Do not introduce LaTeX, plasTeX, or leanblueprint as a source pipeline.
- Do not make JavaScript compute dependency semantics. Python emits all node status, DOT attributes, and modal payloads.
- Do not remove `graph.json`; downstream tools may already depend on it.
- Prefer adding `dep_graph_document.html` while keeping `graph.html` working. Leanblueprint users expect the former; existing mdblueprint docs and tests expect the latter.
- Keep node ids as stable HTML ids after deterministic escaping. Use readable display labels derived from the final id component, e.g. `algebra.group_identity_unique` -> `group_identity_unique`.

## Concrete Implementation Path

Implement this as a presentation-layer migration, not as a publisher rewrite.
The safest path is bottom-up:

1. Stabilize semantics in Python first.
   - Add a pure `blueprint_view` layer that can be tested without Jinja or browser rendering.
   - Treat this as the only place where `mdblueprint` status values become leanblueprint-style display states.
   - Keep current `KnowledgeGraph` edge storage unchanged and reverse edges only in the presentation view.
2. Add deterministic DOT generation before touching HTML.
   - DOT output should be fully reproducible from `KnowledgeGraph`.
   - DOT should be inspected in tests for edge direction, node shape, labels, and color attributes.
   - `graph.json` remains the machine API and must not change shape.
3. Wire publisher data once.
   - `publish()` should compute `blueprint_graph`, `blueprint_dot`, and a node-id-to-view map once.
   - Templates receive view models; templates should not recompute readiness, ancestors, edge direction, or DOT attributes.
4. Replace graph rendering next.
   - Generate `dep_graph_document.html` first.
   - Write the same content to `graph.html` as compatibility.
   - Use Graphviz/DOT rendering and leanblueprint-like modals.
   - Decide CDN-with-SRI versus vendored assets before merging this issue.
5. Replace node page rendering after graph page is wired.
   - Node pages use the same `BlueprintNodeView` as graph modals.
   - Uses and Lean declarations become modal payloads.
   - Markdown body remains the mathematical content source.
6. Polish overview and topic pages last.
   - These should be thin navigation surfaces over the same generated node pages.
   - Avoid expanding scope into search, filters, or project dashboards.
7. Do browser QA only after all pages render.
   - String tests are enough for deterministic HTML generation.
   - Browser testing is needed for Graphviz rendering, modal behavior, MathJax, and responsive layout.
8. Document the boundary.
   - The docs must explicitly say the project borrows leanblueprint's output style only.
   - Markdown remains the durable source; Python owns graph semantics.

The dependency chain is:

```text
#20 presentation model
  -> #21 publisher wiring
      -> #22 graph page
      -> #23 node pages
          -> #24 overview/topic/navigation
              -> #25 browser QA
                  -> #26 docs/release checklist
```

## GitHub Issue Breakdown

Development is tracked through these issues:

| Issue | Scope | Depends on | Exit Gate |
|---|---|---|---|
| #20 Phase 5.1: Leanblueprint presentation model and DOT semantics | Python view model, status/shape mapping, reversed display edges, deterministic DOT | none | `tests/test_blueprint_view.py` and relevant export tests pass |
| #21 Phase 5.2: Publisher wiring and Graphviz asset strategy | `publish.py` wiring, `dep_graph_document.html` output, compatibility `graph.html`, JS asset decision | #20 | publisher writes the new graph artifacts without changing `graph.json` |
| #22 Phase 5.3: Leanblueprint-style dependency graph page | Graphviz page template, legend, graph node modals, graph interaction JS | #20, #21 | generated graph page contains DOT, legend, modals, and no Cytoscape dependency |
| #23 Phase 5.4: Blueprint theorem-wrapper node pages | theorem/definition wrapper node pages, Uses modal, Lean modal, theorem-style CSS | #20, #21 | definition/theorem pages render leanblueprint-style wrappers |
| #24 Phase 5.5: Blueprint overview, topic pages, and navigation | index/topic/base navigation polish | #23, can start after #22 | index and topic pages link to the dependency graph and use compact blueprint summaries |
| #25 Phase 5.6: Browser and visual QA for generated blueprint site | browser verification, responsive layout, modal behavior, graph nonblank checks | #22, #23, #24 | desktop and mobile browser checks pass; any layout bugs are fixed |
| #26 Phase 5.7: Documentation and release checklist for leanblueprint-style publisher | README, publisher docs, final verification checklist | #25 | docs explain the Markdown/leanblueprint boundary and full verification passes |

## Issue Workflow

- Work one issue at a time unless two issues have disjoint files and the dependency chain allows parallel work.
- Prefer one branch/PR per issue:
  - `codex/phase-5-1-blueprint-view`
  - `codex/phase-5-2-publisher-wiring`
  - `codex/phase-5-3-graph-page`
  - `codex/phase-5-4-node-pages`
  - `codex/phase-5-5-overview-topic`
  - `codex/phase-5-6-browser-qa`
  - `codex/phase-5-7-docs`
- Each PR should close exactly one issue unless the change is a tiny follow-up from browser QA.
- Every issue branch must run the issue-specific tests plus any directly affected existing tests.
- The final issue closes only after:
  - `uv run python -m tools.knowledge.check docs/knowledge`
  - `uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-leanblueprint-style-site`
  - `uv run pytest`
  - browser QA for graph and node pages

---

### Task 1: Add Blueprint Presentation Model

**Files:**
- Create: `tools/knowledge/blueprint_view.py`
- Create: `tests/test_blueprint_view.py`

- [ ] **Step 1: Write failing tests for view-model mapping**

Create `tests/test_blueprint_view.py` with tests covering captions, shapes, display labels, readiness, color classes, DOT attributes, edge direction, and `fully_proved`.

```python
from tools.knowledge.blueprint_view import (
    build_blueprint_graph,
    display_label,
    html_id,
    kind_caption,
    node_shape,
)
from tools.knowledge.graph import build_graph
from tools.knowledge.models import Node, Verification


def test_kind_caption_and_shape():
    assert kind_caption("definition") == "Definition"
    assert kind_caption("theorem") == "Theorem"
    assert node_shape("definition") == "box"
    assert node_shape("theorem") == "ellipse"
    assert node_shape("example") == "note"


def test_display_label_uses_last_id_component():
    assert display_label("algebra.group_identity_unique") == "group_identity_unique"


def test_html_id_is_stable_and_selector_safe():
    assert html_id("algebra.group_identity_unique") == "node-algebra-2e-group_identity_unique"


def test_dependency_edges_are_reversed_for_display():
    base = Node(id="t.base", title="Base", kind="definition", status="admitted")
    thm = Node(id="t.thm", title="Theorem", kind="theorem", status="admitted", uses=["t.base"])
    graph, diags = build_graph([base, thm])
    assert diags == []

    view = build_blueprint_graph(graph)

    assert view.edges == [("t.base", "t.thm")]


def test_formalization_status_mapping():
    base = Node(
        id="t.base",
        title="Base",
        kind="definition",
        status="formalized",
        verification=Verification(definition="accepted", proof="not_applicable", alignment="aligned"),
    )
    thm = Node(
        id="t.thm",
        title="Theorem",
        kind="theorem",
        status="proved",
        uses=["t.base"],
        verification=Verification(statement="accepted", proof="accepted", alignment="aligned"),
    )
    graph, diags = build_graph([base, thm])
    assert diags == []

    view = build_blueprint_graph(graph)
    by_id = {node.id: node for node in view.nodes}

    assert by_id["t.base"].border_state == "stated"
    assert by_id["t.base"].fill_state == "defined"
    assert by_id["t.thm"].border_state == "stated"
    assert by_id["t.thm"].fill_state == "fully_proved"


def test_staged_node_is_not_ready():
    staged = Node(id="t.future", title="Future", kind="definition", status="staged")
    graph, diags = build_graph([staged])
    assert diags == []

    view = build_blueprint_graph(graph)

    assert view.nodes[0].border_state == "not_ready"
    assert view.nodes[0].fill_state is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_blueprint_view.py -q
```

Expected: FAIL because `tools.knowledge.blueprint_view` does not exist.

- [ ] **Step 3: Implement `tools/knowledge/blueprint_view.py`**

Implement a pure presentation module with dataclasses and deterministic helpers.

```python
"""Leanblueprint-style presentation view models."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from tools.knowledge.graph import KnowledgeGraph
from tools.knowledge.models import DEFINITION_KINDS, Node


THEOREM_LIKE_KINDS = frozenset({"lemma", "proposition", "theorem", "external-theorem", "proof-plan"})


@dataclass(frozen=True)
class BlueprintNodeView:
    id: str
    html_id: str
    label: str
    title: str
    caption: str
    kind: str
    status: str
    shape: str
    border_state: str | None = None
    fill_state: str | None = None
    lean_declarations: tuple[str, ...] = ()
    uses: tuple[str, ...] = ()
    used_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlueprintGraphView:
    nodes: list[BlueprintNodeView] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


def display_label(node_id: str) -> str:
    return node_id.rsplit(".", 1)[-1]


def html_id(node_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "-" for ch in node_id)
    return f"node-{safe}"


def dot_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def kind_caption(kind: str) -> str:
    return {
        "concept": "Concept",
        "definition": "Definition",
        "lemma": "Lemma",
        "proposition": "Proposition",
        "theorem": "Theorem",
        "external-theorem": "External theorem",
        "proof-plan": "Proof plan",
        "example": "Example",
        "task": "Task",
    }.get(kind, kind.replace("-", " ").title())


def node_shape(kind: str) -> str:
    if kind in DEFINITION_KINDS:
        return "box"
    if kind in THEOREM_LIKE_KINDS:
        return "ellipse"
    if kind == "example":
        return "note"
    if kind == "task":
        return "component"
    return "box"


def _deps_ready(node: Node, g: KnowledgeGraph) -> bool:
    for dep_id in node.uses:
        dep = g.nodes.get(dep_id)
        if dep is None or dep.status in {"staged", "needs_statement_review", "needs_definition_review", "needs_proof_review", "blocked"}:
            return False
    return True


def _ancestors(node_id: str, g: KnowledgeGraph) -> set[str]:
    seen: set[str] = set()
    stack = list(g.edges.get(node_id, []))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(g.edges.get(current, []))
    return seen


def _border_state(node: Node, g: KnowledgeGraph) -> str | None:
    if node.status in {"formalized", "proved"}:
        return "stated"
    if node.status in {"staged", "needs_statement_review", "needs_definition_review", "needs_proof_review", "blocked"}:
        return "not_ready"
    if node.status == "admitted" and _deps_ready(node, g):
        return "can_state"
    return None


def _fill_state(node: Node, g: KnowledgeGraph) -> str | None:
    if node.kind in DEFINITION_KINDS and node.status in {"formalized", "proved"}:
        return "defined"
    if node.status == "proved":
        ancestor_ids = _ancestors(node.id, g)
        if all(g.nodes[aid].status in {"formalized", "proved"} or g.nodes[aid].kind in DEFINITION_KINDS for aid in ancestor_ids):
            return "fully_proved"
        return "proved"
    if node.status == "admitted" and _deps_ready(node, g) and node.kind in THEOREM_LIKE_KINDS:
        return "can_prove"
    return None


def build_blueprint_graph(g: KnowledgeGraph) -> BlueprintGraphView:
    nodes: list[BlueprintNodeView] = []
    for node_id in sorted(g.nodes):
        node = g.nodes[node_id]
        lean_decls = tuple(node.lean.declarations) if node.lean else ()
        nodes.append(
            BlueprintNodeView(
                id=node.id,
                html_id=html_id(node.id),
                label=display_label(node.id),
                title=node.title,
                caption=kind_caption(node.kind),
                kind=node.kind,
                status=node.status,
                shape=node_shape(node.kind),
                border_state=_border_state(node, g),
                fill_state=_fill_state(node, g),
                lean_declarations=lean_decls,
                uses=tuple(sorted(g.edges.get(node.id, []))),
                used_by=tuple(sorted(g.reverse_edges.get(node.id, []))),
            )
        )

    edges: list[tuple[str, str]] = []
    for dependent in sorted(g.edges):
        for dependency in sorted(g.edges[dependent]):
            edges.append((dependency, dependent))

    return BlueprintGraphView(nodes=nodes, edges=edges)


def dot_node_attributes(view: BlueprintNodeView) -> dict[str, str]:
    attrs = {
        "label": view.label,
        "shape": view.shape,
        "penwidth": "1.8",
        "URL": f"#{escape(view.html_id)}",
    }
    if view.border_state == "stated":
        attrs["color"] = "green"
    elif view.border_state == "can_state":
        attrs["color"] = "blue"
    elif view.border_state == "not_ready":
        attrs["color"] = "#FFAA33"

    if view.fill_state == "defined":
        attrs["fillcolor"] = "#B0ECA3"
        attrs["style"] = "filled"
    elif view.fill_state == "proved":
        attrs["fillcolor"] = "#9CEC8B"
        attrs["style"] = "filled"
    elif view.fill_state == "can_prove":
        attrs["fillcolor"] = "#A3D6FF"
        attrs["style"] = "filled"
    elif view.fill_state == "fully_proved":
        attrs["fillcolor"] = "#1CAC78"
        attrs["style"] = "filled"
    return attrs


def graph_to_dot(view: BlueprintGraphView) -> str:
    lines = [
        'strict digraph "" {',
        "\tgraph [bgcolor=transparent];",
        '\tnode [label="\\N", penwidth=1.8];',
        "\tedge [arrowhead=vee];",
    ]
    for node in view.nodes:
        attrs = dot_node_attributes(node)
        attr_text = ", ".join(f"{key}={dot_quote(value)}" for key, value in sorted(attrs.items()))
        lines.append(f"\t{dot_quote(node.id)} [{attr_text}];")
    for source, target in view.edges:
        lines.append(f"\t{dot_quote(source)} -> {dot_quote(target)} [style=dashed];")
    lines.append("}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
uv run pytest tests/test_blueprint_view.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add tools/knowledge/blueprint_view.py tests/test_blueprint_view.py
git commit -m "feat: add leanblueprint presentation model"
```

---

### Task 2: Export Leanblueprint-Style Graph Data

**Files:**
- Modify: `tools/knowledge/export.py`
- Modify: `tests/test_export.py`

- [ ] **Step 1: Write failing tests for DOT export and non-breaking JSON**

Append tests to `tests/test_export.py`.

```python
from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot


def test_blueprint_dot_uses_dependency_to_dependent_direction():
    nodes = scan_directory(NODES_DIR)
    g, _ = build_graph(nodes)
    view = build_blueprint_graph(g)
    dot = graph_to_dot(view)

    assert '"algebra.group" -> "algebra.group_homomorphism"' in dot


def test_blueprint_dot_uses_leanblueprint_shapes():
    nodes = scan_directory(NODES_DIR)
    g, _ = build_graph(nodes)
    view = build_blueprint_graph(g)
    dot = graph_to_dot(view)

    assert 'shape="box"' in dot
    assert 'shape="ellipse"' in dot


def test_existing_graph_json_shape_is_unchanged():
    nodes = scan_directory(NODES_DIR)
    g, _ = build_graph(nodes)
    data = export_graph_json(g)

    assert set(data) == {"nodes", "edges"}
    assert {"from": "algebra.group_homomorphism", "to": "algebra.group"} in data["edges"]
```

- [ ] **Step 2: Run tests to verify failures or current behavior**

Run:

```bash
uv run pytest tests/test_export.py -q
```

Expected: PASS if Task 1 already added `graph_to_dot`; otherwise fail before Task 1 is complete. The important invariant is that `export_graph_json()` remains unchanged.

- [ ] **Step 3: Add explicit export helper if needed**

If templates should not import `blueprint_view` directly, add this helper to `tools/knowledge/export.py`.

```python
from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot


def export_blueprint_dot(g: KnowledgeGraph) -> str:
    return graph_to_dot(build_blueprint_graph(g))
```

- [ ] **Step 4: Run export tests**

Run:

```bash
uv run pytest tests/test_export.py tests/test_blueprint_view.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add tools/knowledge/export.py tests/test_export.py
git commit -m "feat: export leanblueprint-style dot graph"
```

---

### Task 3: Wire Publisher Data and Static Assets

**Files:**
- Modify: `tools/knowledge/publish.py`
- Create: `tools/knowledge/templates/graph.js`
- Modify: `tests/test_publish.py`

- [ ] **Step 1: Write failing publisher tests**

Add tests to `tests/test_publish.py`.

```python
def test_generates_leanblueprint_graph_page(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    site = tmp_path / "site"

    assert (site / "dep_graph_document.html").exists()
    assert (site / "graph.html").exists()
    assert (site / "graph.js").exists()

    graph_page = (site / "dep_graph_document.html").read_text()
    assert "Dependency graph" in graph_page
    assert "Legend" in graph_page
    assert "strict digraph" in graph_page
    assert "algebra.group" in graph_page


def test_graph_page_contains_node_modals(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()

    assert "dep-modal-container" in graph_page
    assert "node-algebra-2e-group-modal" in graph_page
    assert "Lean declarations" in graph_page
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_publish.py::TestPublish::test_generates_leanblueprint_graph_page tests/test_publish.py::TestPublish::test_graph_page_contains_node_modals -q
```

Expected: FAIL because `dep_graph_document.html` and `graph.js` are not generated.

- [ ] **Step 3: Modify `publish.py` to build blueprint views**

Add imports:

```python
from tools.knowledge.blueprint_view import build_blueprint_graph, graph_to_dot
```

After `g, _ = build_graph(all_nodes)`, add:

```python
    blueprint_graph = build_blueprint_graph(g)
    blueprint_dot = graph_to_dot(blueprint_graph)
    blueprint_nodes = {view.id: view for view in blueprint_graph.nodes}
```

Copy `graph.js` with the existing CSS copy:

```python
    shutil.copy(TEMPLATE_DIR / "graph.js", output_dir / "graph.js")
```

Render `dep_graph_document.html` and keep `graph.html` as the same content:

```python
    tmpl = env.get_template("graph.html")
    graph_html = tmpl.render(
        title="Dependency graph",
        root="",
        topics=topic_names,
        graph_dot=blueprint_dot,
        graph_nodes=blueprint_graph.nodes,
    )
    (output_dir / "dep_graph_document.html").write_text(graph_html, encoding="utf-8")
    (output_dir / "graph.html").write_text(graph_html, encoding="utf-8")
```

When rendering node pages, pass each node's presentation view:

```python
                    node_view=blueprint_nodes[node.id],
```

- [ ] **Step 4: Create `tools/knowledge/templates/graph.js`**

```javascript
(function () {
  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function showModal(nodeId) {
    document.querySelectorAll(".dep-modal-container").forEach((modal) => {
      modal.hidden = true;
    });
    const modal = document.getElementById(nodeId + "-modal");
    if (modal) {
      modal.hidden = false;
      modal.querySelector(".dep-closebtn")?.focus();
    }
  }

  function bindGraphInteractions() {
    document.querySelectorAll("#graph .node").forEach((node) => {
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", "button");
      node.addEventListener("click", () => {
        const title = node.querySelector("title")?.textContent?.trim();
        const mapped = title ? document.querySelector(`[data-graph-node="${cssEscape(title)}"]`) : null;
        if (mapped) showModal(mapped.id);
      });
      node.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          node.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        }
      });
    });
  }

  function closeModals() {
    document.querySelectorAll(".dep-modal-container").forEach((modal) => {
      modal.hidden = true;
    });
  }

  window.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#legend-title")?.addEventListener("click", () => {
      document.querySelector("#legend-list")?.toggleAttribute("hidden");
    });
    document.querySelectorAll(".dep-closebtn").forEach((button) => {
      button.addEventListener("click", closeModals);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModals();
    });

    const graphElement = document.getElementById("graph");
    const dotElement = document.getElementById("graph-dot");
    if (!graphElement || !dotElement || !window.d3) return;

    const dot = dotElement.textContent;
    const width = graphElement.clientWidth || 960;
    const height = graphElement.clientHeight || 720;
    window.d3.select("#graph")
      .graphviz({ useWorker: true })
      .width(width)
      .height(height)
      .fit(true)
      .renderDot(dot)
      .on("end", bindGraphInteractions);
  });
})();
```

- [ ] **Step 5: Run publisher tests**

Run:

```bash
uv run pytest tests/test_publish.py -q
```

Expected: PASS after templates are updated in Task 4. If this task runs before Task 4, failures should identify missing template variables/classes only.

- [ ] **Step 6: Commit Task 3**

```bash
git add tools/knowledge/publish.py tools/knowledge/templates/graph.js tests/test_publish.py
git commit -m "feat: wire leanblueprint graph publishing"
```

---

### Task 4: Replace Graph Template With Leanblueprint-Style DAG Page

**Files:**
- Modify: `tools/knowledge/templates/graph.html`
- Modify: `tools/knowledge/templates/style.css`
- Modify: `tests/test_publish.py`

- [ ] **Step 1: Write failing content tests for graph styling**

Add tests to `tests/test_publish.py`.

```python
def test_graph_page_uses_graphviz_assets(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()

    assert "d3-graphviz" in graph_page
    assert 'id="graph-dot"' in graph_page
    assert 'id="graph"' in graph_page
    assert 'id="Legend"' in graph_page


def test_graph_page_has_leanblueprint_legend_entries(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    graph_page = (tmp_path / "site" / "dep_graph_document.html").read_text()

    assert "Boxes" in graph_page
    assert "definitions" in graph_page
    assert "Ellipses" in graph_page
    assert "theorems and lemmas" in graph_page
    assert "Blue border" in graph_page
    assert "Green background" in graph_page
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run:

```bash
uv run pytest tests/test_publish.py::TestPublish::test_graph_page_uses_graphviz_assets tests/test_publish.py::TestPublish::test_graph_page_has_leanblueprint_legend_entries -q
```

Expected: FAIL until `graph.html` is replaced.

- [ ] **Step 3: Replace `tools/knowledge/templates/graph.html`**

Use this template structure.

```html
{% extends "base.html" %}
{% block content %}
<header class="graph-header">
  <a class="toc" href="{{ root }}index.html">Home</a>
  <h1 id="doc_title">Dependencies</h1>
</header>

<section id="Legend" class="graph-legend" aria-label="Dependency graph legend">
  <button id="legend-title" class="legend-title" type="button">
    Legend <span class="legend-bars" aria-hidden="true"><span></span><span></span><span></span></span>
  </button>
  <dl id="legend-list" class="legend-list" hidden>
    <dt>Boxes</dt><dd>definitions</dd>
    <dt>Ellipses</dt><dd>theorems and lemmas</dd>
    <dt>Blue border</dt><dd>the statement is ready to be formalized; all prerequisites are done</dd>
    <dt>Orange border</dt><dd>the statement is not ready to be formalized; the blueprint needs more work</dd>
    <dt>Blue background</dt><dd>the proof is ready to be formalized; all prerequisites are done</dd>
    <dt>Green border</dt><dd>the statement is formalized</dd>
    <dt>Green background</dt><dd>the proof is formalized</dd>
    <dt>Dark green background</dt><dd>the proof and all ancestors are formalized</dd>
  </dl>
</section>

<div id="graph" class="dep-graph" aria-label="Dependency graph"></div>
<script id="graph-dot" type="text/plain">{{ graph_dot }}</script>

<div id="statements" class="dep-statements">
  {% for graph_node in graph_nodes %}
  <div
    class="dep-modal-container"
    id="{{ graph_node.html_id }}-modal"
    data-graph-node="{{ graph_node.id }}"
    hidden
  >
    <div class="dep-modal-content">
      <button class="dep-closebtn" type="button" aria-label="Close">x</button>
      <article class="thm {{ graph_node.kind }}_thmwrapper theorem-style-{{ graph_node.kind }}">
        <header class="{{ graph_node.kind }}_thmheading thm-heading">
          <span class="{{ graph_node.kind }}_thmcaption thm-caption">{{ graph_node.caption }}</span>
          <span class="{{ graph_node.kind }}_thmlabel thm-label">{{ graph_node.label }}</span>
          <span class="{{ graph_node.kind }}_thmtitle thm-title">{{ graph_node.title }}</span>
          <span class="thm-status thm-status-{{ graph_node.status }}">{{ graph_node.status }}</span>
        </header>
        <div class="{{ graph_node.kind }}_thmcontent thm-content">
          <p><a href="{{ root }}{{ graph_node.id.split('.')[0] }}/{{ graph_node.id | replace('.', '_') }}.html">Open node page</a></p>
          {% if graph_node.lean_declarations %}
          <h2>Lean declarations</h2>
          <ul class="uses">
            {% for decl in graph_node.lean_declarations %}
            <li><code>{{ decl }}</code></li>
            {% endfor %}
          </ul>
          {% endif %}
        </div>
      </article>
    </div>
  </div>
  {% endfor %}
</div>

<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@hpcc-js/wasm@2.20.0/dist/index.min.js"
        crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-graphviz@5.6.0/build/d3-graphviz.min.js"
        crossorigin="anonymous"></script>
<script src="{{ root }}graph.js"></script>
{% endblock %}
```

Before implementation, verify and add SRI hashes for the pinned CDN scripts, following the existing repository pattern for MathJax and Cytoscape. If SRI hashes cannot be established reliably, vendor the minified files under `tools/knowledge/templates/vendor/` and copy them in `publish.py`.

- [ ] **Step 4: Add graph CSS to `style.css`**

Append leanblueprint-inspired graph styles without removing existing reusable styles.

```css
.graph-header {
  align-items: center;
  display: flex;
  min-height: 3rem;
  position: relative;
}
.graph-header .toc {
  color: inherit;
  margin-right: auto;
  text-decoration: none;
}
.graph-header h1 {
  left: 50%;
  position: absolute;
  transform: translateX(-50%);
}
.dep-graph {
  border: 1px solid var(--border);
  height: min(78vh, 900px);
  min-height: 560px;
  overflow: hidden;
  resize: both;
  width: 100%;
}
.graph-legend {
  margin: 0.5rem 0 1rem;
  position: relative;
}
.legend-title {
  align-items: center;
  background: transparent;
  border: 0;
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 1.2rem;
  font-weight: 700;
  gap: 0.5rem;
}
.legend-bars span {
  background: var(--text);
  border-radius: 1px;
  display: block;
  height: 3px;
  margin-top: 2px;
  width: 22px;
}
.legend-list {
  background: white;
  border: 1px solid var(--border);
  box-shadow: 0 4px 16px rgb(0 0 0 / 12%);
  display: grid;
  gap: 0.35rem 0.75rem;
  grid-template-columns: max-content 1fr;
  left: 0;
  max-width: min(42rem, 90vw);
  padding: 1rem;
  position: absolute;
  top: 2.5rem;
  z-index: 3;
}
.legend-list dt {
  font-weight: 700;
}
.dep-modal-container {
  inset: 4rem 5vw auto;
  position: fixed;
  z-index: 10;
}
.dep-modal-content {
  background: white;
  border: 1px solid #497da5;
  border-radius: 5px;
  box-shadow: 0 4px 8px rgb(0 0 0 / 20%), 0 6px 20px rgb(0 0 0 / 19%);
  margin: auto;
  max-height: 80vh;
  overflow: auto;
  padding: 0.75rem 1rem;
}
.dep-closebtn {
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 700;
  position: absolute;
  right: 1rem;
  top: 1rem;
}
#graph .node {
  cursor: pointer;
}
```

- [ ] **Step 5: Run publisher tests**

Run:

```bash
uv run pytest tests/test_publish.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add tools/knowledge/templates/graph.html tools/knowledge/templates/style.css tests/test_publish.py
git commit -m "feat: render leanblueprint-style dependency graph"
```

---

### Task 5: Render Node Pages as Blueprint Objects

**Files:**
- Modify: `tools/knowledge/templates/node.html`
- Modify: `tools/knowledge/templates/style.css`
- Modify: `tools/knowledge/publish.py`
- Modify: `tests/test_publish.py`

- [ ] **Step 1: Write failing tests for theorem-wrapper node pages**

Add tests to `tests/test_publish.py`.

```python
def test_node_page_uses_theorem_wrapper(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    page = (tmp_path / "site" / "algebra" / "algebra_group_identity_unique.html").read_text()

    assert "theorem_thmwrapper" in page
    assert "theorem_thmcaption" in page
    assert "Group Identity Is Unique" in page
    assert "thm_header_hidden_extras" in page


def test_definition_page_uses_definition_wrapper(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    page = (tmp_path / "site" / "algebra" / "algebra_group.html").read_text()

    assert "definition_thmwrapper" in page
    assert "definition_thmcaption" in page
    assert "Group" in page


def test_node_page_has_uses_and_lean_modals(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    page = (tmp_path / "site" / "algebra" / "algebra_group_identity_unique.html").read_text()

    assert "Uses" in page
    assert "Lean declarations" in page
    assert "Algebra.Group.identity_unique" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_publish.py::TestPublish::test_node_page_uses_theorem_wrapper tests/test_publish.py::TestPublish::test_definition_page_uses_definition_wrapper tests/test_publish.py::TestPublish::test_node_page_has_uses_and_lean_modals -q
```

Expected: FAIL until `node.html` is updated.

- [ ] **Step 3: Replace `node.html` with theorem-wrapper markup**

Use this structure.

```html
{% extends "base.html" %}
{% block content %}
<article class="{{ node.kind }}_thmwrapper theorem-style-{{ node.kind }} node-page" id="{{ node_view.html_id }}">
  <header class="{{ node.kind }}_thmheading thm-heading">
    <span class="{{ node.kind }}_thmcaption thm-caption">{{ node_view.caption }}</span>
    <span class="{{ node.kind }}_thmlabel thm-label">{{ node_view.label }}</span>
    <span class="{{ node.kind }}_thmtitle thm-title">{{ node.title }}</span>
    <div class="thm_header_extras">
      {% if node.status in ["formalized", "proved"] %}<span class="checkmark">✓</span>{% endif %}
      <span class="badge kind-{{ node.kind }}">{{ node.kind }}</span>
      <span class="badge status-{{ node.status }}">{{ node.status }}</span>
    </div>
    <div class="thm_header_hidden_extras">
      <a class="permalink" href="#{{ node_view.html_id }}">#</a>
      {% if deps %}
      <button class="modal-trigger" type="button" data-modal-target="uses-modal">Uses</button>
      {% endif %}
      {% if node.lean %}
      <button class="modal-trigger lean" type="button" data-modal-target="lean-modal">L∃∀N</button>
      {% endif %}
    </div>
  </header>

  {% if deps %}
  <div class="modal-container" id="uses-modal" hidden>
    <div class="modal-content">
      <header><h1>Uses</h1><button class="closebtn" type="button">x</button></header>
      <ul class="uses">
        {% for dep in deps %}
        <li><a href="{{ dep.href }}">{{ dep.id }}</a> — {{ dep.title }}</li>
        {% endfor %}
      </ul>
    </div>
  </div>
  {% endif %}

  {% if node.lean %}
  <div class="modal-container" id="lean-modal" hidden>
    <div class="modal-content">
      <header><h1>Lean declarations</h1><button class="closebtn" type="button">x</button></header>
      <ul class="uses">
        {% for decl in node.lean.declarations %}
        <li><code>{{ decl }}</code></li>
        {% endfor %}
      </ul>
    </div>
  </div>
  {% endif %}

  <div class="{{ node.kind }}_thmcontent thm-content body">
    {{ body_html | safe }}
  </div>

  {% if dependents %}
  <section class="deps deps-used-by">
    <h2>Used by</h2>
    <ul>
      {% for dep in dependents %}
      <li><a href="{{ dep.href }}">{{ dep.id }}</a> — {{ dep.title }}</li>
      {% endfor %}
    </ul>
  </section>
  {% endif %}

  {% if node.tags %}
  <footer class="tags">
    {% for tag in node.tags %}<span class="tag">{{ tag }}</span>{% endfor %}
  </footer>
  {% endif %}
</article>
{% endblock %}
```

- [ ] **Step 4: Add modal JavaScript for node pages**

Either reuse `graph.js` for all modal triggers by renaming it to `site.js`, or add a short inline script in `base.html`. Prefer a shared static file:

```javascript
document.querySelectorAll(".modal-trigger").forEach((button) => {
  button.addEventListener("click", () => {
    const target = button.getAttribute("data-modal-target");
    if (target) document.getElementById(target)?.removeAttribute("hidden");
  });
});
document.querySelectorAll(".closebtn").forEach((button) => {
  button.addEventListener("click", () => {
    button.closest(".modal-container")?.setAttribute("hidden", "");
  });
});
```

If this is put in `graph.js`, rename the file to `site.js` and update `publish.py`, `base.html`, and graph template references in the same task.

- [ ] **Step 5: Add theorem-wrapper CSS**

Append to `style.css`.

```css
.thm-heading {
  align-items: baseline;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding-bottom: 0.35rem;
}
.thm-caption {
  font-weight: 700;
}
.thm-label {
  color: #555;
  font-weight: 600;
}
.thm-title {
  font-weight: 600;
}
.thm_header_extras,
.thm_header_hidden_extras {
  align-items: center;
  display: inline-flex;
  gap: 0.35rem;
  margin-left: auto;
}
.thm-content {
  border-left: 0.12rem solid #222;
  line-height: 1.7;
  margin-top: 0.9rem;
  padding-left: 0.9rem;
}
.definition_thmcontent,
.concept_thmcontent {
  border-left-color: #497da5;
}
.lemma_thmcontent,
.proposition_thmcontent,
.theorem_thmcontent,
.external-theorem_thmcontent {
  border-left-color: #222;
}
.modal-trigger {
  background: var(--badge-bg);
  border: 1px solid var(--border);
  border-radius: 3px;
  cursor: pointer;
  font: inherit;
  font-size: 0.8rem;
  padding: 0.1rem 0.35rem;
}
.modal-container {
  inset: 4rem 5vw auto;
  position: fixed;
  z-index: 20;
}
.modal-content {
  background: white;
  border: 1px solid #497da5;
  border-radius: 5px;
  box-shadow: 0 4px 8px rgb(0 0 0 / 20%), 0 6px 20px rgb(0 0 0 / 19%);
  max-height: 80vh;
  overflow: auto;
  padding: 1rem;
}
.modal-content header {
  align-items: center;
  display: flex;
  gap: 1rem;
}
.closebtn {
  margin-left: auto;
}
```

- [ ] **Step 6: Run publisher tests**

Run:

```bash
uv run pytest tests/test_publish.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add tools/knowledge/templates/node.html tools/knowledge/templates/style.css tools/knowledge/publish.py tests/test_publish.py
git commit -m "feat: render node pages as blueprint objects"
```

---

### Task 6: Polish Overview and Topic Pages

**Files:**
- Modify: `tools/knowledge/templates/index.html`
- Modify: `tools/knowledge/templates/topic.html`
- Modify: `tools/knowledge/templates/base.html`
- Modify: `tools/knowledge/templates/style.css`
- Modify: `tests/test_publish.py`

- [ ] **Step 1: Write failing overview tests**

Add tests to `tests/test_publish.py`.

```python
def test_index_links_to_dependency_graph_with_leanblueprint_name(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    page = (tmp_path / "site" / "index.html").read_text()

    assert "dep_graph_document.html" in page
    assert "Dependency graph" in page


def test_topic_page_has_blueprint_summary_classes(self, tmp_path):
    publish(KNOWLEDGE_ROOT, tmp_path / "site")
    page = (tmp_path / "site" / "algebra" / "index.html").read_text()

    assert "blueprint-node-list" in page
    assert "definition_thmcaption" in page
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/test_publish.py::TestPublish::test_index_links_to_dependency_graph_with_leanblueprint_name tests/test_publish.py::TestPublish::test_topic_page_has_blueprint_summary_classes -q
```

Expected: FAIL until templates are updated.

- [ ] **Step 3: Update `base.html` navigation**

Change the graph nav link:

```html
<a class="nav-link" href="{{ root }}dep_graph_document.html">Dependency graph</a>
```

Keep the logo and topic list. Do not remove `graph.html` generation.

- [ ] **Step 4: Update `index.html`**

Use an overview that preserves the current scannable table.

```html
{% extends "base.html" %}
{% block content %}
<section class="blueprint-overview">
  <h1>Knowledge Base</h1>
  <p>{{ node_count }} nodes across {{ topic_count }} topics.</p>
  <p><a href="dep_graph_document.html">Dependency graph</a></p>
</section>

<table class="node-table">
  <thead>
    <tr><th>ID</th><th>Title</th><th>Kind</th><th>Status</th></tr>
  </thead>
  <tbody>
  {% for node in nodes %}
    <tr>
      <td><a href="{{ node.href }}">{{ node.id }}</a></td>
      <td>{{ node.title }}</td>
      <td><span class="badge kind-{{ node.kind }}">{{ node.kind }}</span></td>
      <td><span class="badge status-{{ node.status }}">{{ node.status }}</span></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Update `topic.html`**

Use compact theorem-style summaries before or instead of the table.

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ topic }}</h1>

<div class="blueprint-node-list">
  {% for node in nodes %}
  <article class="{{ node.kind }}_thmwrapper theorem-style-{{ node.kind }} summary-node">
    <header class="{{ node.kind }}_thmheading thm-heading">
      <span class="{{ node.kind }}_thmcaption thm-caption">{{ node.kind | replace("-", " ") | title }}</span>
      <span class="{{ node.kind }}_thmlabel thm-label">{{ node.id.split(".")[-1] }}</span>
      <a class="{{ node.kind }}_thmtitle thm-title" href="{{ node.id | replace('.', '_') }}.html">{{ node.title }}</a>
      <span class="badge status-{{ node.status }}">{{ node.status }}</span>
    </header>
  </article>
  {% endfor %}
</div>
{% endblock %}
```

- [ ] **Step 6: Add CSS for overview/topic summaries**

```css
.blueprint-overview {
  margin-bottom: 1.5rem;
}
.blueprint-node-list {
  display: grid;
  gap: 0.75rem;
}
.summary-node {
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.5rem;
}
.summary-node .thm-title {
  color: var(--accent);
  text-decoration: none;
}
.summary-node .thm-title:hover {
  text-decoration: underline;
}
```

- [ ] **Step 7: Run publisher tests**

Run:

```bash
uv run pytest tests/test_publish.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add tools/knowledge/templates/index.html tools/knowledge/templates/topic.html tools/knowledge/templates/base.html tools/knowledge/templates/style.css tests/test_publish.py
git commit -m "feat: polish blueprint overview pages"
```

---

### Task 7: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/publisher-and-dag.md`

- [ ] **Step 1: Update README status and generated-site description**

Edit README to say:

```markdown
The publisher keeps Markdown nodes as the durable source and generates a
leanblueprint-style static site: theorem/definition wrappers, Uses and Lean
declaration modals, and a Graphviz-style dependency graph. It does not use
LaTeX, plasTeX, or leanblueprint as the source pipeline.
```

- [ ] **Step 2: Update `docs/publisher-and-dag.md`**

Add a section:

```markdown
## Leanblueprint-Style Output

The generated site intentionally follows leanblueprint's presentation style
without adopting its TeX/plasTeX source model.

- Python emits all graph semantics and DOT attributes.
- Browser JavaScript renders the DOT and handles modal interaction only.
- Dependencies display as `dependency -> dependent`.
- Definitions use box nodes; theorem-like nodes use ellipse nodes.
- Status and formalization fields determine border and fill colors.
```

- [ ] **Step 3: Run full verification**

Run:

```bash
uv run python -m tools.knowledge.check docs/knowledge
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-leanblueprint-style-site
uv run pytest
```

Expected:

```text
0 error(s), 0 warning(s)
Published to /tmp/mdblueprint-leanblueprint-style-site
all tests pass
```

- [ ] **Step 4: Inspect generated files manually**

Run:

```bash
find /tmp/mdblueprint-leanblueprint-style-site -maxdepth 2 -type f | sort
rg -n "strict digraph|dep-modal-container|definition_thmwrapper|theorem_thmwrapper|Dependency graph" /tmp/mdblueprint-leanblueprint-style-site
```

Expected:

- `dep_graph_document.html` exists.
- `graph.html` still exists.
- `graph.js` exists.
- Node pages contain theorem/definition wrapper classes.
- Graph page contains the DOT string and modal containers.

- [ ] **Step 5: Commit Task 7**

```bash
git add README.md docs/publisher-and-dag.md
git commit -m "docs: describe leanblueprint-style publisher"
```

---

## Final Acceptance Criteria

- Markdown remains the only durable source format for mdblueprint nodes.
- No LaTeX, plasTeX, or leanblueprint package is required to publish the site.
- `graph.json` remains backward-compatible.
- The generated site includes `dep_graph_document.html` and keeps `graph.html`.
- The graph visually follows leanblueprint:
  - Graphviz/DOT layout
  - box definitions
  - ellipse theorem-like nodes
  - dependency-to-dependent edge direction
  - leanblueprint-like legend
  - clickable node modals
- Node pages visually follow leanblueprint theorem wrappers.
- Existing validation still reports `0 error(s), 0 warning(s)`.
- Full test suite passes with `uv run pytest`.

## Risks and Mitigations

- CDN/SRI risk: pin script versions and add SRI hashes, or vendor graph rendering assets if hashes are awkward to verify.
- Browser graph rendering risk: keep `graph.json` and DOT embedded in HTML so the generated graph remains inspectable even if JS fails.
- Style drift risk: use leanblueprint class names where useful (`definition_thmwrapper`, `theorem_thmwrapper`, `uses`, `dep-modal-container`) so future comparisons are straightforward.
- Semantics risk: keep all readiness and formalization mapping in Python tests, not in JavaScript.

## Execution Recommendation

Use subagent-driven execution task by task if implementation is split across workers. If executing inline, complete one task and run its tests before starting the next task.
