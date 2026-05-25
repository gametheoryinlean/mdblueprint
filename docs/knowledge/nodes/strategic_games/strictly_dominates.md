---
id: strategic_games.strictly_dominates
title: Strict Dominance
kind: definition
status: admitted
uses:
  - strategic_games.unilateral_deviation
lean:
  modules:
    - GameTheoryLib.StrategicGame.Dominance
  declarations:
    - StrategicGame.StrictlyDominates
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Section 2.3"
      format: section
      note: "Definition of strict dominance"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this stated for arbitrary games?"
  verdict: "Yes. Strict inequality for all opponent profiles."
tags:
  - strategic-game
  - dominance
topic_lean_alignment: divergent
---

# Strict Dominance

A strategy $s_i$ strictly dominates another strategy $s'_i$ for player $i$ if, for
every profile $\sigma$ of the other players, playing $s_i$ yields strictly higher
payoff:

$$\forall \sigma, \quad u_i(\sigma[i \mapsto s'_i]) < u_i(\sigma[i \mapsto s_i]).$$
