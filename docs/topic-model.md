# Topic Model

mdblueprint separates node ownership from graph browsing views. A node has one
home topic for authoring and file ownership, but it may appear in several topic
views in the generated site and DAG.

## Terms

- `kind: topic` is a node kind for a roadmap-level mathematical subject that has
  not yet been decomposed into individual definitions, constructions, examples,
  standard theorems, references, and Lean targets. It is distinct from the
  `topics` membership field below. Do not make `topic` a synthetic node id
  prefix; use a mathematical id such as `root_data_and_duality.root_data`.
- `id` is the stable machine identity of a node. It should remain stable across
  topic view changes.
- `primary_topic` is the node's home topic. It is a canonical hierarchical topic
  id and determines the default owner, default topic page, and ordinary file
  placement.
- `topics` is the list of graph and index views that should include the node.
  It may contain more than one topic id. The `primary_topic` must be included in
  `topics`.
- `uses` is the logical dependency list by node id. It is not topic membership.
- `tags` are keywords for search and keyword pages. They are not topic
  membership and do not create DAG edges.

Example:

```yaml
id: algebra.groups.identity_unique
title: Identity Is Unique
kind: theorem
status: admitted
primary_topic: algebra.groups
topics:
  - algebra.groups
  - algebra.monoids
uses:
  - algebra.groups.group
tags:
  - identity
```

The same node may appear in both the `algebra.groups` and `algebra.monoids`
topic views, but it remains one node with one id and one home topic.

## File Placement

Files should be placed according to the home topic:

```text
docs/knowledge/nodes/<home-topic-root>/...
docs/knowledge/staged/<home-topic-root>/...
```

Projects may mirror the full hierarchical topic path in directories when that
is useful, but path layout is an authoring convention, not the definition of
topic membership. For compatibility, tooling derives a fallback home topic from
the node id when `primary_topic` and `topics` are absent.

## Topic Catalogs

Each meaningful knowledge folder may contain a reserved `topics.md` catalog.
The exact filename `topics.md` is reserved and must not be parsed as a knowledge
node.

A folder-level `topics.md` lists only the immediate topics and subtopics that
are relevant at that folder level. It should not duplicate the whole global
tree. The full topic id should appear in each entry so authors and agents do not
invent near-duplicate names.

The human catalog complements the machine registry in `mdblueprint.yml`:

- `mdblueprint.yml` stores canonical topic ids, titles, aliases, and future
  machine selectors.
- `topics.md` explains local scope boundaries and nearby subtopics for humans
  and agents.

## Graph Semantics

Topic DAG artifacts are browsing projections of the full machine graph.

- `graph.json` remains the full node-level graph.
- Topic overview and subgraph artifacts group nodes by `topics` membership.
- A node with multiple topic memberships may appear in multiple topic pages and
  topic subgraphs.
- Global node counts count unique node ids. Per-topic counts count nodes visible
  in that topic view, so counts across topics are not necessarily additive.
- Topic edges summarize ordinary `uses` dependencies between visible topic
  memberships. Proof-plan route dependencies remain separate from ordinary
  theorem dependencies.

Changing a node's topic membership changes where the node is shown. It does not
change the mathematical dependency DAG unless `uses` changes.
