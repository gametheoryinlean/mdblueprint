---
id: strategic_games.strategy_profile
title: Strategy Profile
kind: definition
status: admitted
uses:
  - strategic_games.strategic_game
lean:
  modules:
    - GameTheoryLib.StrategicGame.Basic
  declarations:
    - StrategicGame.Profile
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2"
      format: section
      note: "Definition of strategy profile"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary player sets?"
  verdict: "Yes, a dependent product over arbitrary player index type."
tags:
  - strategic-game
  - foundational
---

# Strategy Profile

Given a strategic game $(I, (S_i), (u_i))$, a strategy profile is a tuple
$\sigma = (\sigma_i)_{i \in I}$ where $\sigma_i \in S_i$ for each player $i$.

In Lean, a profile is `∀ i, G.strategy i`.
