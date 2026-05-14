# Node Template

```markdown
---
id: <topic>.<name>
title: <Title>
kind: <definition | lemma | theorem | example | ...>
status: <staged | admitted>
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
verification:
  statement: <accepted | needs_revision | rejected>  # for theorem kinds
  # OR
  definition: <accepted | needs_revision | rejected>  # for definition kinds
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
