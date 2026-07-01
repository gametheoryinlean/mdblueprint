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

<Statement, proof, motivation — written in ordinary mathematical
language. Cross-reference other nodes with `[[id]]`. Inline mentions of
declarations listed in `lean.declarations` (e.g. `welfare_can_be_zero`)
auto-link to the Lean source URL.>

<No Lean syntax in the prose: avoid `⊤`, `↑t`, `WithTop`, `Lex (F × B)`,
`toLex`/`ofLex`, `Fin n`, `Function.Injective`, internal Lean lemma
names, Lean code blocks. Push all of that down into the section below.>

## Lean formalization

<Optional section describing the Lean design: type signatures, key
structure fields, structural lemmas the proof goes through, and any
design-rationale paragraphs that explain *why* the Lean formalization
is shaped the way it is. Lean identifiers and code blocks are
expected here.>
```
