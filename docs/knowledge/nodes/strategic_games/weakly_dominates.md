---
id: strategic_games.weakly_dominates
title: Weak Dominance
kind: definition
status: admitted
uses:
  - strategic_games.unilateral_deviation
lean:
  modules:
    - GameTheoryLib.StrategicGame.Dominance
  declarations:
    - StrategicGame.WeaklyDominates
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Section 2.3"
      format: section
      note: "Definition of weak dominance"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this stated for arbitrary games or restricted to finite games?"
  verdict: "For arbitrary games. No finiteness assumption."
tags:
  - strategic-game
  - dominance
topic_lean_alignment: divergent
---

# Weak Dominance

A strategy $s_i$ weakly dominates another strategy $s'_i$ for player $i$ if, for
every profile $\sigma$ of the other players, playing $s_i$ yields at least as high
a payoff as playing $s'_i$:

$$\forall \sigma, \quad u_i(\sigma[i \mapsto s'_i]) \le u_i(\sigma[i \mapsto s_i]).$$
