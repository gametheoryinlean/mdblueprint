---
id: algebra.group_isomorphism
title: Group Isomorphism
kind: definition
status: admitted
uses:
  - algebra.group_homomorphism
lean:
  modules:
    - MyLibrary.Algebra.GroupIsomorphism
  declarations:
    - Algebra.GroupIsomorphism
source:
  artifacts:
    - id: algebra-text
      path: references/algebra-text.pdf
  spans:
    - artifact: algebra-text
      locator: "Chapter 1, Definition 1.12"
      format: section
      note: "Definition of a group isomorphism"
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary groups?"
  verdict: "Yes, no cardinality or commutativity hypothesis is present."
tags:
  - algebra
  - morphism
---

# Group Isomorphism

Let $G$ and $H$ be groups. A group isomorphism from $G$ to $H$ is a bijective
group homomorphism.
