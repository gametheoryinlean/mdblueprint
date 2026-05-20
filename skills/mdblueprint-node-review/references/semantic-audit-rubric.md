# Semantic Audit Rubric

Five gates that every math node must pass before an admission recommendation.
Apply all gates and record verdicts in the review report `semantic_audit` block
(see `review-report-schema.md`).

## Gate 1: Formal Core Gate

**Applies to:** definition, concept, lemma, proposition, theorem, external-theorem

A node passes when its body contains a sentence that mathematically defines an
object, property, or relation (for definition/concept nodes), or states explicit
hypotheses and a conclusion (for theorem-like nodes).

Failure patterns:

- body is entirely expository prose with no defining sentence
- body says "X is [description]" without any mathematical characterisation
- theorem body summarises a result without stating it precisely

Verdict: `pass` | `fail`

**Example failure — descriptive definition:**

```markdown
# Compact Set

A compact set is an important concept in topology that arises in many contexts
and has useful properties. It is studied extensively in analysis.
```

No definition is present; the body is purely motivational.

**Example failure — vague theorem:**

```markdown
# Intermediate Value Theorem

Continuous functions on closed intervals behave nicely and take all intermediate
values. This is useful in many proofs.
```

No hypotheses or conclusion are stated.

## Gate 2: Non-Descriptive Content Gate

**Applies to:** definition, concept, lemma, proposition, theorem, external-theorem

A node passes when the formal core is the primary content. A short motivation
paragraph before the definition is acceptable; the definition itself must be
present and precise.

Failure patterns:

- body is mostly background text with only a vague closing sentence
- definition is hedged with "roughly", "informally", or "can be thought of as"

Verdict: `pass` | `fail`

**Example failure — hedged definition:**

```markdown
# Group

Roughly speaking, a group is a set with a binary operation that behaves like
addition or multiplication. More formally, it satisfies certain axioms that we
will not list here.
```

The hedge and the omitted axioms mean no precise definition is present.

## Gate 3: Dependency Grounding Gate

**Applies to:** all math nodes

A node passes when every concept used in the formal core either is defined in
the node body itself or is reachable through a `uses` entry that points to a
node defining it.

Failure patterns:

- undefined symbol in the definition or theorem statement not covered by `uses`
- `uses` contains topical references or reading-order prerequisites, not genuine
  logical dependencies
- a core concept appears in neither the body nor `uses`

Verdict: `pass` | `fail` | `unverifiable`

Use `unverifiable` when the dependency nodes are unavailable or the body does not
expose enough structure to trace symbols.

**Example failure — undefined symbol:**

```markdown
# Continuous Function

A function $f : X \to Y$ is continuous when every inverse image
$f^{-1}(U)$ of an open set $U$ is open.
```

If `uses` does not reference nodes defining "open set" and "inverse image",
this gate fails.

## Gate 4: Source/Reference Gate

**Applies to:** definition, concept, lemma, proposition, theorem, external-theorem

A node passes when it has at least one `source.spans` entry with a specific
locator (page number, section, theorem number, or URL).

Failure patterns:

- no `source` section at all
- `source` has `artifacts` but no `spans`
- spans exist but locators are generic ("see textbook" without a number)

A project may opt out of this gate by setting `sources.require_source_spans:
false` in `mdblueprint.yml`; when the project requires sources, a missing span
is grounds for a revision request.

Verdict: `pass` | `fail` | `waived`

## Gate 5: Lean Link vs Alignment Gate

**Applies to:** nodes with a `lean:` block or `verification.alignment`

A `lean:` block is a mechanical reference only — it does not constitute semantic
alignment evidence. A node passes this gate when it does not claim alignment
status based solely on the presence of a `lean:` block.

Failure patterns:

- `verification.alignment: aligned` without a corresponding alignment review
  report under `docs/knowledge/reviews/`
- admission recommendation treats Lean reference existence as proof of alignment
- `status: formalized` or `status: proved` without verified Lean declarations

Verdict: `pass` | `fail` | `not_applicable`
