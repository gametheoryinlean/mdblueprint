---
id: strategic_games.unilateral_deviation
title: Unilateral Deviation
kind: definition
status: admitted
uses:
  - strategic_games.strategy_profile
lean:
  modules:
    - GameTheoryLib.StrategicGame.Basic
  declarations:
    - StrategicGame.Profile.deviate
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2"
      format: section
      note: "Notation for unilateral deviation"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this defined for arbitrary player sets and strategy spaces?"
  verdict: "Yes, uses Function.update which works for any dependent function."
tags:
  - strategic-game
  - foundational
---

# Unilateral Deviation

Given a strategy profile $\sigma$ and a player $i$, the unilateral deviation
$(\sigma_{-i}, s'_i)$ is the profile where player $i$ plays $s'_i$ and all other
players play according to $\sigma$. We write $\sigma[i \mapsto s']$.

In Lean, this is `Function.update σ i s'`.
