---
id: strategic_games.best_response
title: Best Response
kind: definition
status: admitted
uses:
  - strategic_games.unilateral_deviation
lean:
  modules:
    - GameTheoryLib.StrategicGame.BestResponse
  declarations:
    - StrategicGame.IsBestResponse
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 2, Section 2.4"
      format: section
      note: "Definition of best response"
verification:
  definition: accepted
  proof: not_applicable
  alignment: aligned
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary strategy spaces?"
  verdict: "Yes, quantifies over all alternative strategies for the player."
tags:
  - strategic-game
  - solution-concept
---

# Best Response

A strategy $\sigma_i$ is a best response for player $i$ to the profile $\sigma$ if
no unilateral deviation can improve $i$'s payoff:

$$\forall s'_i \in S_i, \quad u_i(\sigma[i \mapsto s'_i]) \le u_i(\sigma).$$
