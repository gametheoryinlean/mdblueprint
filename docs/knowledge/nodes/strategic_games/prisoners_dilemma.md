---
id: strategic_games.prisoners_dilemma
title: Prisoner's Dilemma
kind: example
status: admitted
uses:
  - strategic_games.nash_equilibrium
  - strategic_games.weakly_dominant_strategy
lean:
  modules:
    - GameTheoryLib.StrategicGame.Examples
  declarations:
    - PrisonersDilemma.PD
    - PrisonersDilemma.pd_defect_weakly_dominant
    - PrisonersDilemma.pd_defect_nash
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Example 2.8"
      format: section
      note: "Prisoner's Dilemma"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
tags:
  - strategic-game
  - example
  - classic
---

# Prisoner's Dilemma

The Prisoner's Dilemma is a two-player strategic game where each player can
Cooperate ($C$) or Defect ($D$). The payoff matrix is:

|       | $C$    | $D$    |
|-------|--------|--------|
| $C$   | (2, 2) | (0, 3) |
| $D$   | (3, 0) | (1, 1) |

Defecting is a weakly dominant strategy for each player. The unique Nash
equilibrium is $(D, D)$ with payoff $(1, 1)$, which is Pareto-dominated by
$(C, C)$ with payoff $(2, 2)$.
