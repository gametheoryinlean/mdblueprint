# Dry-Run Plan Schema

Use this schema when a graph-refactor report contains concrete mechanical
actions that should be simulated before any admitted node files are edited.

The dry-run tool reads the knowledge base and this plan, applies operations in
memory, then reports before/after graph counts and diagnostic deltas. It does
not write node files.

```bash
uv run python -m tools.knowledge.refactor_dry_run docs/knowledge <plan.yml> --json
```

```yaml
operations:
  - op: remove-dependency
    node_id: <node id>
    dependency: <dependency id>
  - op: add-dependency
    node_id: <node id>
    dependency: <dependency id>
  - op: move-primary-topic
    node_id: <node id>
    topic: <topic id>
  - op: add-topic-membership
    node_id: <node id>
    topic: <topic id>
  - op: remove-topic-membership
    node_id: <node id>
    topic: <topic id>
  - op: mark-lean-topic-divergent
    node_id: <node id>
  - op: delete-node
    node_id: <node id>
```

Only use `delete-node` for impact simulation. A deletion proposal still needs
human review and formulation-sensitive descendant analysis before any actual
file removal.
