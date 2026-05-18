# Node Template

```markdown
---
id: <stable.node.id>
title: <Title>
kind: <definition | lemma | theorem | example | ...>
status: <staged | admitted>
primary_topic: <canonical.home.topic>
topics:
  - <canonical.home.topic>
  - <optional.additional.topic>
uses:
  - <dependency.node.id>
lean:
  modules:
    - <Lean.Module.Name>
  declarations:
    - <LeanDeclarationName>
source:
  artifacts:
    - id: <artifact-id>
      path: <relative/path>
  spans:
    - artifact: <artifact-id>
      locator: "<locator string>"
      format: <book-page | section | arxiv-theorem | lean-location | url>
      note: "<optional note>"
verification:                          # pick ONE of statement/definition:
  statement: <accepted | needs_revision | rejected>   # theorem, lemma, proposition, external-theorem
  definition: <accepted | needs_revision | rejected>  # definition
  proof: <accepted | gap | critical | not_applicable>
  alignment: <aligned | pending | mismatch>
generality:
  reviewed: <true | false>
  prompt: "<generality question>"
  verdict: "<answer>"
tags:
  - <tag>
---

# <Title>

<Mathematical content only. No operational sections.>
```
