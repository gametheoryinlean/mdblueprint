# Node Format

Each node is one Markdown file. The YAML frontmatter stores system information. The Markdown body stores only mathematics.

## Example

```markdown
---
id: extensive_games.subgame_perfect_equilibrium
title: Subgame Perfect Equilibrium
kind: definition
status: admitted
uses:
  - extensive_games.subgame
lean:
  modules:
    - GameTheory.ExtensiveForm.SubgamePerfect
  declarations:
    - ExtensiveGame.SubgamePerfectEquilibrium
source:
  artifacts:
    - references/game-theory-book.pdf
  spans:
    - locator: "Chapter 4, page 123"
      note: "Definition of subgame perfect equilibrium"
verification:
  statement: accepted
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary finite extensive games?"
  verdict: "Yes, with the finiteness assumption explicit."
tags:
  - extensive-game
  - equilibrium
---

# Subgame Perfect Equilibrium

Let $G$ be a finite extensive-form game. A strategy profile $\sigma$ is a
subgame perfect equilibrium if, for every subgame $H$ of $G$, the restriction
of $\sigma$ to $H$ is a Nash equilibrium of $H$.
```

## Body Rule

The body must not contain operational sections such as:

- status;
- implementation notes;
- Lean interface;
- task checklist;
- agent discussion;
- reviewer metadata.

Those belong in YAML, `reviews/`, or `requests/`.

## Node Kinds

The first version supports:

```text
concept
definition
lemma
proposition
theorem
example
proof-plan
external-theorem
task
```

`task` nodes are allowed only for mathematical work items that participate in the knowledge graph. Routine project management should not be placed in the mathematical node body.

## Status Model

Use a small status vocabulary:

```text
staged
needs_statement_review
needs_definition_review
needs_proof_review
admitted
formalized
proved
blocked
deprecated
```

Only files under `docs/knowledge/nodes/` should normally have `admitted`, `formalized`, or `proved` status.

Files under `docs/knowledge/staged/` are proposals even if their YAML says the mathematical content looks plausible.

## Required Structural Checks

Deterministic Python tools should fail with clear diagnostics for:

- missing required YAML fields;
- invalid status or kind;
- duplicate node ids;
- missing dependencies;
- dependency cycles;
- malformed Lean references;
- node body containing forbidden operational headings;
- generated graph output not matching parsed nodes.
