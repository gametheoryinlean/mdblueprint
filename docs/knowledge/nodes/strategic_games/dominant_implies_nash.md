---
id: strategic_games.dominant_implies_nash
title: Dominant Strategy Profile is a Nash Equilibrium
kind: theorem
status: admitted
uses:
  - strategic_games.nash_equilibrium
  - strategic_games.weakly_dominant_strategy
lean:
  modules:
    - GameTheoryLib.StrategicGame.NashEquilibrium
  declarations:
    - StrategicGame.IsNashEquilibrium.of_dominant
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2"
      format: section
      note: "Relationship between dominant strategies and Nash equilibrium"
verification:
  statement: accepted
  proof: accepted
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this the standard relationship between dominance and Nash?"
  verdict: "Yes. If every player has a weakly dominant strategy, the resulting profile is Nash."
tags:
  - strategic-game
  - equilibrium
  - dominance
---

# Dominant Strategy Profile is a Nash Equilibrium

If every player $i$ plays a weakly dominant strategy $s_i$, then the resulting
profile $\sigma = (s_i)_{i \in I}$ is a Nash equilibrium.

*Proof.* A weakly dominant strategy weakly dominates every alternative. In particular,
for any player $i$ and any deviation $s'_i$, we have
$u_i(\sigma[i \mapsto s'_i]) \le u_i(\sigma)$. This means each player is best
responding, so $\sigma$ is a Nash equilibrium. $\square$
