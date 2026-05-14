---
id: strategic_games.mixed_strategy
title: Mixed Strategy
kind: definition
status: staged
uses:
  - strategic_games.strategic_game
lean:
  modules:
    - GameTheoryLib.StrategicGame.MixedStrategy
  declarations:
    - StrategicGame.MixedStrategy
source:
  artifacts:
    - id: msz
      path: references/maschler-solan-zamir.pdf
  spans:
    - artifact: msz
      locator: "Chapter 3"
      format: section
      note: "Mixed strategies and mixed extensions"
tags:
  - strategic-game
  - mixed-strategy
---

# Mixed Strategy

A mixed strategy for player $i$ is a probability distribution over the strategy
set $S_i$. When $S_i$ is finite, a mixed strategy is a vector
$x_i \in \Delta(S_i)$ in the standard simplex.
