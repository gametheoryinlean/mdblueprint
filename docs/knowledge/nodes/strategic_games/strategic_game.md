---
id: strategic_games.strategic_game
title: Strategic Game
kind: definition
status: admitted
uses: []
lean:
  modules:
    - GameTheoryLib.StrategicGame.Basic
  declarations:
    - StrategicGame
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2"
      format: section
      note: "Definition of strategic-form game"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary player sets and strategy spaces?"
  verdict: "Yes, parameterized by player type ι and strategy spaces per player."
tags:
  - strategic-game
  - foundational
topic_lean_alignment: divergent
---

# Strategic Game

A strategic game (or normal-form game) is a tuple $(I, (S_i)_{i \in I}, (u_i)_{i \in I})$
where $I$ is a set of players, $S_i$ is the strategy set of player $i$, and
$u_i \colon \prod_{j \in I} S_j \to U$ is the payoff function of player $i$.

In the Lean formalization, this is a structure with fields `strategy : ι → Type*` and
`payoff : Profile → ι → U`, where `Profile = ∀ i, strategy i`.
