---
id: algebra.group_homomorphism
title: Group Homomorphism
kind: definition
status: admitted
uses:
  - algebra.group
lean:
  modules:
    - MyLibrary.Algebra.GroupHomomorphism
  declarations:
    - Algebra.GroupHomomorphism
source:
  artifacts:
    - id: algebra-text
      path: references/algebra-text.pdf
  spans:
    - artifact: algebra-text
      locator: "Chapter 1, Definition 1.8"
      format: section
      note: "Definition of a group homomorphism"
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary groups?"
  verdict: "Yes, the source and node impose no extra hypotheses."
tags:
  - algebra
  - morphism
---

# Group Homomorphism

Let $G$ and $H$ be groups. A group homomorphism from $G$ to $H$ is a function
$f : G \to H$ such that $f(xy) = f(x)f(y)$ for all $x,y \in G$.
