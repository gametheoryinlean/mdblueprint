---
name: mdblueprint-node-author
description: Use when creating or editing Markdown knowledge nodes for an mdblueprint knowledge base.
---

# mdblueprint-node-author

Create or edit Markdown knowledge nodes by hand.

## When to use

When authoring mathematical content for the knowledge base.

## Checklist

- [ ] Read `docs/knowledge/mdblueprint.yml` first; if `topics` is configured, use canonical topic ids from the registry, not aliases.
- [ ] Read the nearest folder-level `topics.md` catalog before choosing topic names.
- [ ] Math-only body — no operational sections (status, implementation notes, etc.)
- [ ] Body reads as ordinary mathematics; no Lean syntax (`⊤`, `↑t`, `WithTop`, `Lex (F × B)`, `toLex`/`ofLex`, `Fin n`, `Function.Injective`, ...) leaks into the prose.
- [ ] Lean design — type names, structure fields, structural lemma names, code blocks, design rationale — lives in a final `## Lean formalization` section, not in the statement or proof.
- [ ] **Every Lean snippet in the `## Lean formalization` section is a fenced code block with the `lean` language tag.** Use ` ```lean ` on its own line to open and ` ``` ` on its own line to close, with a blank line before and after the block. Single identifiers cited inline use `` `code spans `` (single backticks). Never paste multi-line Lean into a paragraph without fences — the renderer only turns fenced blocks into `<pre><code>`; unfenced Lean pastes render as running prose and lose all indentation and structure.
- [ ] **Field-coverage audit before finalizing.** When the node declares a `structure`, `class`, or `inductive` in its `lean.declarations`, run `python -m tools.knowledge.kb_lean_field_audit <knowledge_root>` and verify zero findings. The audit checks that every field of a declared class/structure is visibly referenced in the KB body (by backticked name, LaTeX-math identifier, axiom tag like `(P0)`, or docstring keyword). A field that appears only in the Lean signature but not in the mathematical body is a real gap — the reader of the KB page cannot see the full definition. Each finding comes with an Agent-actionable suggestion: add an axiom bullet with the matching tag, or reference the data field in the definition body.
- [ ] **Do NOT call structure fields, typeclass fields, or hypotheses "axioms".** In Lean 4, `axiom foo : P` is a specific declaration form that postulates `P` without proof and adds it to the kernel — a genuine mathematical assumption. Fields of a `structure` (like `P0`, `P1`, `P2` on `InductionDatum`) or of a `class` (like `smul_dim` on `GCellComplex`) are NOT axioms — they are **proof obligations** the constructor supplies. When writing a "which conditions are consumed" table in a KB body, use "Hypotheses used", "Conditions used", "Structure fields consumed", or "Datum fields used" — never "Axioms used". Reserve the word "axiom" for Lean-kernel-level `axiom` declarations. See `references/lean-formalization-section.md` for the extended discussion.
- [ ] Cross-references use the bare `[[id]]` form; theorem identifiers in `**Theorem (`name`, ...)**` headings are fine (they auto-link to source).
- [ ] **Linking is Python's job, not the author's.** YAML `lean.declarations` lists only the node's *core* declarations (the statement/definition the node is about, plus key helper lemmas the rendered Lean panel should surface). Helper or internal lemma names cited inline in the body are resolved automatically by the project-wide Lean index; do not pad YAML to make them link.
- [ ] **Names in the body track the Lean namespace.** When Lean renames a namespace or type, the node title and prose must follow within the same change. If you see `Old.Name` in Lean and `Old.Name`/`old-name-rule` in prose: rename both, don't leave the prose stale.
- [ ] **Body is library-independent, not a textbook restatement.** Do not put source-internal numbering (`Problem 2.1(b)`, "the impossibility half of Problem X", "the three parts of Problem Y", "Theorem (Author, Section 4.2)") into the body. Theorem headings name the library identifier only: `**Theorem (`my_thm_name`).**`, never `**Theorem (`my_thm_name`, Author Problem 4.2).**`. Source locators live in `## References`.
- [ ] **No editorial / motivational sections.** A serious blueprint records mathematical content; the reader's interest is presumed. Forbidden heading patterns: `## Why it matters`, `## Significance`, `## Importance`, `## Where this shows up`, `## Discussion` (when editorial). Genuine technical remarks (tightness of a hypothesis, comparison of alternative hypotheses, failure mechanism of a counterexample, design rationale) are fine — use descriptive headings (`## Tightness of …`, `## Identity injectivity vs. value injectivity`, `## Mechanism of the failure`), not `Why X matters`.
- [ ] **No defensive re-justification of correctly-quantified statements.** If the theorem statement already quantifies "for every $n \ge 1$", do not add a Remarks bullet arguing "why $n$, not just $n = 2$". The statement speaks for itself.
- [ ] Structured YAML metadata following node-format.md
- [ ] TeX uses supported delimiters and project macros from math-authoring.md
- [ ] Stable node id; do not change it just to alter graph topic membership
- [ ] One `primary_topic` home topic and a `topics` list containing every graph view that should include the node
- [ ] One concept, definition, theorem, example, or proof-plan per file
- [ ] Correct verification fields for the node kind (statement for theorems, definition for definitions)
- [ ] Source spans with artifact binding if content comes from a reference
- [ ] Incomplete statements marked with review status, not hidden

## Must not

- Must not set `status: admitted` without review evidence — use `staged` for new content.
- Must not write operational content (implementation notes, status tracking, TODOs) in the Markdown body.
- Must not leak Lean syntax into statements, proofs, or motivation. If the prose needs a concept that only exists as a Lean construct, describe it in English (or as ordinary math) and put the Lean specifics in `## Lean formalization`.
- Must not paste multi-line Lean into a `<p>` context. Every code block inside `## Lean formalization` uses the fenced form ` ```lean ` … ` ``` `. Leaving the language tag off (` ``` ` alone) is still acceptable but discouraged; omitting the fences entirely is a bug — the code renders as running paragraph text with backticks visible.
- Must not frame the body with one source's internal numbering. The library is independent — it cites sources, it does not re-state them. See `docs/node-format.md` § "External-Reference Conventions".
- Must not write editorial / motivational sections (`## Why it matters`, `## Significance`, etc.). A blueprint is not a textbook; it records mathematical content, not editorial commentary on why the content is interesting.
- Must not invent dependencies beyond what can be justified from the source or existing nodes.
- Must not invent a topic not in the canonical registry or nearest `topics.md`; if no topic fits, propose one in a request instead of silently inventing a name.

## Must read

- `docs/node-format.md`
- `docs/topic-model.md`
- `docs/math-authoring.md`
- `references/node-template.md`
- `references/lean-formalization-section.md` (mandatory when the node has a `lean:` YAML field)
- `docs/knowledge/mdblueprint.yml` (topic registry)
- nearest `topics.md` catalog when present
