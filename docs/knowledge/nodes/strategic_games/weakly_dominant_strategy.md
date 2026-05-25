---
id: strategic_games.weakly_dominant_strategy
title: Weakly Dominant Strategy
kind: definition
status: admitted
uses:
  - strategic_games.weakly_dominates
lean:
  modules:
    - GameTheoryLib.StrategicGame.Dominance
  declarations:
    - StrategicGame.IsWeaklyDominant
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Section 2.3"
      format: section
      note: "Definition of weakly dominant strategy"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this stated for arbitrary games?"
  verdict: "Yes. A strategy that weakly dominates all alternatives."
tags:
  - strategic-game
  - dominance
---

# Weakly Dominant Strategy

A strategy $s_i$ is weakly dominant for player $i$ if it weakly dominates every
other strategy available to $i$:

$$\forall s'_i \in S_i, \quad s_i \text{ weakly dominates } s'_i.$$
