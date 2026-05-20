# Node Audit States

Each node in the audit pipeline is assigned exactly one state. The coordinator
uses `tools.knowledge.lean_audit.determine_node_audit_state` to compute the
initial state, then subagent outputs may move a node to a more resolved state.

## State vocabulary

| State | Meaning |
|-------|---------|
| `missing_lean` | Node has no `lean:` block. Send to Link Finder. |
| `lean_ref_broken` | Node has `lean:` but one or more `lean.declarations` cannot be resolved in the indexed Lean repo. Send to Lean Ref Checker. |
| `lean_ref_ambiguous` | Node has `lean:` but a declaration name matches multiple qualified names. Send to Lean Ref Checker. |
| `pending_alignment` | Lean references resolve mechanically but `verification.alignment` is not `aligned`. Send to Alignment Verifier. |
| `aligned` | Lean references resolve and `verification.alignment: aligned` with a supporting review report. |
| `minor_repair_possible` | Alignment Verifier returned a non-`aligned` classification but the Repair Classifier says `small_fix`. Awaiting coordinator approval. |
| `major_revision_needed` | Repair Classifier returned `large_revision`. Requires user confirmation before any change. |
| `cannot_fix_without_hint` | Repair Classifier returned `cannot_fix` or `needs_user_hint`. Blocked until user provides guidance. |
| `needs_lean_generation` | Link Finder returned `needs_lean_generation`: no matching declaration exists yet. |

## State transitions

```
missing_lean
  → [Link Finder: link]         → pending_alignment
  → [Link Finder: no_match]     → (report written, stays missing_lean)
  → [Link Finder: ambiguous]    → (report written, stays missing_lean)
  → [Link Finder: needs_lean_generation] → needs_lean_generation
  → [Link Finder: needs_human_decision]  → (request written, stays missing_lean)

lean_ref_broken / lean_ref_ambiguous
  → [Lean Ref Checker: resolved]   → pending_alignment
  → [Lean Ref Checker: broken]     → lean_ref_broken  (report written)
  → [Lean Ref Checker: ambiguous]  → lean_ref_ambiguous (report written)
  → [Lean Ref Checker: suspicious] → pending_alignment with risk note

pending_alignment
  → [Alignment Verifier: aligned]  → aligned
  → [Alignment Verifier: other]    → [Repair Classifier]
      → small_fix                  → minor_repair_possible
      → large_revision             → major_revision_needed
      → cannot_fix                 → cannot_fix_without_hint
      → needs_user_hint            → cannot_fix_without_hint
```

## Coordinator responsibilities per state

- `missing_lean`: write `needs_lean_<ts>.md` under `docs/knowledge/requests/`
  if Link Finder cannot find a match.
- `lean_ref_broken`: write ref check report under `docs/knowledge/reviews/`.
- `minor_repair_possible`: write repair report; do not apply without approval.
- `major_revision_needed`: write repair report; block until user confirms.
- `cannot_fix_without_hint`: write repair report; await user hint.
