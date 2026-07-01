# Writing the `## Lean formalization` section

Every node whose YAML `lean:` field is populated should end with a
`## Lean formalization` section.  It is the *only* place where Lean
identifiers, code, and Mathlib references appear — the body above it
is ordinary mathematics.

This document specifies the formatting rules and gives four typical
patterns.

## Formatting rules

1. **Section heading is exactly** `## Lean formalization` (no
   variant — no "Lean formalisation", no "Lean formalizations", no
   subsection numbering).
2. **Fenced code blocks are mandatory for multi-line Lean.**
   - Open with a line containing exactly ` ```lean `.
   - Close with a line containing exactly ` ``` `.
   - **Blank line before the opening fence and after the closing
     fence** — otherwise adjacent paragraphs merge with the block
     under Python-Markdown's paragraph rules, and the block becomes
     hard to reflow.
   - Do **not** indent the fences under a list bullet — the renderer
     treats them as list continuation text.  If you need code inside
     a list, break out of the list first.
3. **Inline identifiers use single backticks:** `` `MulAction.stabilizer` ``,
   `` `pointwiseFix` ``, `` `d.G'` ``.  Never inline a multi-line
   snippet with `<br>` or `\`.
4. **Language tag `lean` is required.**  The renderer keys style and
   future syntax highlighting off the tag; omitting it produces a
   plain `<pre><code>` (correct but styleless).
5. **Keep the Lean prose descriptive of the object, not the paper.**
   Per AGENTS.md: describe the Lean declaration on its own terms.
   Do not write "the paper's `lem:foo`"; write "the setwise cell
   stabiliser `MulAction.stabilizer G E`".

## Pattern 1: single-declaration node

Use when the node is about *one* Lean definition or theorem.

```markdown
## Lean formalization

`SheafOnBuilding.Foo.bar` is the direct Lean rendering:

​```lean
theorem bar (x : X) : P x := by
  ...
​```

The proof uses `baz` from the ambient typeclass; no project-specific
imports beyond `SheafOnBuilding.Basic`.
```

## Pattern 2: umbrella / topic node with a mapping table

Use when the node covers several Lean pieces at once (e.g. a
"standing setup" node listing the four classes that instantiate it).

```markdown
## Lean formalization

The standing typeclass stack:

| Ingredient | Kind | Lean signature | KB node |
|---|---|---|---|
| face poset + dimension | data-carrying `class` | `class AbstractCellComplex (X) [PartialOrder X]` | [[node:...]] |
| local finiteness | Prop-valued `class` | `class IsLocallyFinite (X) [PartialOrder X] : Prop` | [[node:...]] |
...

Every downstream file is stated against the variable block

​```lean
variable {G : Type*} [Group G]
variable {X : Type*}
variable [PartialOrder X] [AbstractCellComplex X] [IsLocallyFinite X]
variable [MulAction G X] [GCellComplex G X]
​```
```

## Pattern 3: proof-clause → Lean-lemma correspondence

Use when the mathematical body proves a proposition with several
clauses, each backed by its own Lean lemma.

```markdown
## Lean formalization

Each clause of the proposition is a separate Lean declaration:

| Clause | Lean lemma | Uses |
|---|---|---|
| Reflexivity | `leRep_refl` | none |
| Transitivity | `leRep_trans` | (P0), (P1) |
| Left descent | `leRep_left_descends` | (P1) |
| ... | ... | ... |

The `PartialOrder` instance packages these into a Mathlib-facing
statement:

​```lean
instance : PartialOrder (InducedSpace d) where
  le := Quotient.lift₂ (leRep d) ⟨left/right descent⟩
  le_refl  := ⟨leRep_refl⟩
  le_trans := ⟨leRep_trans⟩
  le_antisymm := ⟨leRep_antisymm⟩
​```
```

## Pattern 4: Mathlib-forwarded fact

Use when the abstract-level content is essentially a rename of a
Mathlib construct.

```markdown
## Lean formalization

The pointwise fixator of a single poset element coincides with
Mathlib's `MulAction.stabilizer G E : Subgroup G`; the membership
predicate is `MulAction.mem_stabilizer_iff`.  No project-local
re-definition is needed and no cell-complex structure is required —
only `[MulAction G X]`.
```

No fenced block needed — the whole content is one paragraph of
prose with three inline identifiers.

## Common mistakes and their symptoms

| Mistake | Rendered symptom |
|---|---|
| Omit the fence entirely | ``` ```lean ``` shows as text; code becomes running prose |
| Fence but no language tag | Correct `<pre><code>` but no syntax coloring hook |
| Fence indented under a `- ` bullet | Block folded into the bullet's `<li>` as continuation text |
| No blank line before opening fence | Python-Markdown attaches the fence to the previous `<p>` |
| Use `<code>` HTML directly around multiline | HTML entities escaped; angle brackets show as `&lt;` |
| Paste Lean into a `> quote` block | Renders as blockquoted text, no `<pre>` |

Test by inspecting the deployed page after publish — if you can see
`` ``` `` in the rendered HTML, the fence didn't take.

## Cross-file consistency

- The identifiers in `## Lean formalization` must exist in the
  repo.  Broken identifiers surface as `[WARNING]` in the validator's
  Lean-index resolution pass, or as `Did you mean:` panels on the
  rendered page.
- The identifiers listed in YAML `lean.declarations` should include
  the ones the section highlights as *core* (statement, main
  theorem, typeclass), not helper lemmas cited only inline — the
  Lean index resolves helpers automatically.
