---
name: mdblueprint-lean-linking
description: Use when a Markdown node needs a proposed lean frontmatter block from a Python-generated bounded candidate bundle of existing Lean declarations.
---

# mdblueprint-lean-linking

Choose existing Lean declarations for one Markdown node from a bounded candidate
bundle. This skill is agent-agnostic: Codex, Claude, OpenCode, or another agent
can follow the same contract.

## Inputs

- target node bundle from `tools.knowledge.lean_link_candidates`;
- candidate Lean declarations, signatures, snippets, and source URLs supplied by
  Python;
- dependency summaries supplied by Python.

Do not scan the whole Lean repo.

## Output Schema

```yaml
agent: lean-linking
node_id: <id>
decision: link | no_match | ambiguous | needs_lean_generation | needs_human_decision
proposed_lean:
  repository: <repo id>
  modules:
    - <Lean.Module>
  declarations:
    - <Lean.Declaration>
primary_declaration: <declaration or null>
role_notes:
  <declaration>: primary_definition | theorem_statement | projection | helper | notation | instance
reason: <short explanation>
risks:
  - <semantic risk or mismatch>
```

Omit `proposed_lean` unless `decision: link`.

## Rules

- A `lean:` block is a mechanical link, not semantic alignment.
- Do not set `verification.alignment`.
- Do not set `status: formalized` or `status: proved`.
- Do not generate new Lean code.
- Do not edit admitted truth directly unless the Python orchestrator asks for a
  patch.
- Choose `no_match` or `ambiguous` when the candidates do not justify a safe
  mechanical link.
