---
id: algebra.group
title: Group
kind: definition
status: admitted
uses: []
lean:
  modules:
    - MyLibrary.Algebra.Group
  declarations:
    - Algebra.Group
source:
  artifacts:
    - id: algebra-text
      path: references/algebra-text.pdf
  spans:
    - artifact: algebra-text
      locator: "Chapter 1, Definition 1.1"
      format: section
      note: "Definition of a group"
verification:
  definition: accepted
  proof: not_applicable
  alignment: pending
generality:
  reviewed: true
  prompt: "Is this definition stated for arbitrary carrier types?"
  verdict: "Yes, no finiteness or commutativity assumption is imposed."
tags:
  - algebra
  - foundational
---

# Group

A group is a type $G$ equipped with a multiplication, identity element, and
inverse operation such that multiplication is associative, the identity acts
on both sides, and every element multiplied by its inverse gives the identity.
