---
id: test.bad_span_ref
title: Bad Span Reference
kind: definition
status: admitted
uses: []
source:
  artifacts:
    - id: book-a
      path: references/book-a.pdf
  spans:
    - artifact: nonexistent-artifact
      locator: "page 1"
      format: book-page
---

# Bad Span Reference

The span references an artifact id that does not exist.
