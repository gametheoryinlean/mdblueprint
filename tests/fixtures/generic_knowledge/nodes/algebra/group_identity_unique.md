---
id: algebra.group_identity_unique
title: Group Identity Is Unique
kind: theorem
status: admitted
uses:
  - algebra.group
lean:
  modules:
    - MyLibrary.Algebra.Group
  declarations:
    - Algebra.Group.identity_unique
source:
  artifacts:
    - id: algebra-text
      path: references/algebra-text.pdf
  spans:
    - artifact: algebra-text
      locator: "Chapter 1, Proposition 1.2"
      format: section
      note: "Uniqueness of the identity element"
verification:
  statement: accepted
  proof: accepted
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this theorem stated for arbitrary groups?"
  verdict: "Yes, the result uses only the group axioms."
tags:
  - algebra
  - theorem
---

# Group Identity Is Unique

In any group, the identity element is unique.

*Proof.*
If $e$ and $e'$ are both identity elements, then $e = ee' = e'$.
