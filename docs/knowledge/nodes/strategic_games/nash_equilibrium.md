---
id: strategic_games.nash_equilibrium
title: Nash Equilibrium
kind: definition
status: admitted
uses:
  - strategic_games.best_response
lean:
  modules:
    - GameTheoryLib.StrategicGame.NashEquilibrium
  declarations:
    - StrategicGame.IsNashEquilibrium
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Section 2.4"
      format: section
      note: "Definition of Nash equilibrium in pure strategies"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this the standard definition for arbitrary strategic games?"
  verdict: "Yes. Every player best responds simultaneously."
tags:
  - strategic-game
  - solution-concept
  - equilibrium
---

# Nash Equilibrium

A strategy profile $\sigma$ is a Nash equilibrium if every player is playing a best
response to the strategies of the other players:

$$\forall i \in I, \quad \sigma_i \text{ is a best response to } \sigma.$$

Equivalently, no player can improve their payoff by a unilateral deviation.
