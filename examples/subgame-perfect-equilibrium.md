---
id: extensive_games.subgame_perfect_equilibrium
title: Subgame Perfect Equilibrium
kind: definition
status: admitted
uses:
  - extensive_games.subgame
lean:
  modules:
    - GameTheory.ExtensiveForm.SubgamePerfect
  declarations:
    - ExtensiveGame.SubgamePerfectEquilibrium
source:
  artifacts:
    - references/game-theory-book.pdf
  spans:
    - locator: "Chapter 4, page 123"
      note: "Definition of subgame perfect equilibrium"
verification:
  statement: accepted
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary finite extensive games?"
  verdict: "Yes, with the finiteness assumption explicit."
tags:
  - extensive-game
  - equilibrium
---

# Subgame Perfect Equilibrium

Let $G$ be a finite extensive-form game. A strategy profile $\sigma$ is a
subgame perfect equilibrium if, for every subgame $H$ of $G$, the restriction
of $\sigma$ to $H$ is a Nash equilibrium of $H$.
