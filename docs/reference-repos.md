# Reference Repositories

Design and implementation should explicitly consult these repositories.

## Rethlas

Local path:

```text
/Users/hoxide/mycodes/Rethlas
```

Remote observed locally:

```text
git@github.com:jiajunma/Rethlas-plus.git
```

Public reference mentioned in design discussion:

```text
https://github.com/frenzymath/Rethlas
```

Use it for:

- role separation between learner, referee, generator, verifier, librarian, and projector;
- the rule that agents propose and review, while durable truth is admitted separately;
- structured reports instead of free-form agent edits;
- the staged candidate versus admitted knowledge distinction;
- role-specific `AGENTS.md` style instructions.

Relevant local files:

```text
docs/ARCHITECTURE.md
docs/RETHLAS_PLUS_SYSTEM_DESIGN.md
docs/PHASE3_LEARNER_REFEREE.md
agents/generation/AGENTS.md
agents/verification/AGENTS.md
agents/learner/AGENTS.md
agents/referee/AGENTS.md
librarian/validator.py
librarian/projector.py
common/kb/types.py
common/events/schema.py
```

Do not migrate in v1:

- Kuzu storage;
- daemon orchestration;
- event bus complexity;
- dashboard complexity;
- mandatory multi-agent runtime.

The mdblueprint v1 adaptation is file-based and Python-generated.

## unipotentrepn

Local path:

```text
/Users/hoxide/mycodes/unipotentrepn
```

Remote observed locally:

```text
git@github.com:jiajunma/unipotentrepn.git
```

Use it for:

- Lean declaration extraction;
- Lean dependency extraction;
- checking that prose references real Lean declarations;
- auditing mismatch between blueprint statements and Lean signatures;
- practical examples of graph cleanup scripts.

Relevant local files:

```text
tools/extract_lean_decls.py
tools/extract_lean_deps.py
tools/check_blueprint_alignment.py
tools/audit_blueprint_lean.py
tools/lift_graph.py
tools/strip_phantom_nodes.py
```

Do not copy its TeX blueprint source model. Only borrow mechanical Lean-indexing and alignment-precheck ideas.

## leanmdblueprint

Local path:

```text
/Users/hoxide/mycodes/leanmdblueprint
```

Remote observed locally:

```text
git@github.com:jiajunma/leanmd.git
```

Use it for:

- Markdown-first entry model;
- registry and frontmatter design;
- graph-oriented presentation ideas;
- entry-level AI alignment review ideas;
- lessons from benchmark reports and static rendering.

Relevant local files:

```text
README.md
docs/PROJECT_PLAN.md
src/frontmatter.ts
src/registry.ts
src/blueprint.ts
src/render.ts
src/lean.ts
src/lsp.ts
src/export.ts
```

Important divergence:

- mdblueprint should implement website and DAG generation in Python, not TypeScript.
- mdblueprint should keep YAML system metadata separate from math-only Markdown bodies.

## gametheorylib

Local path:

```text
/Users/hoxide/mycodes/gametheorylib
```

Remote observed locally:

```text
git@github.com:gametheoryinlean/gametheorylib.git
```

Use it as one optional reference repository and a concrete fixture for domain examples.
It must not be treated as the default Lean target or as a hard-coded assumption in
generic mdblueprint docs, tools, or skills.

Relevant local files and areas:

```text
blueprint/src/content.tex
blueprint/lean_decls
docs/dev/research/library_blueprint/
docs/dev/research/*_tasks/
GameTheoryLib/
```

Use it to test whether mdblueprint can represent a nontrivial Lean-adjacent mathematical library without relying on a TeX blueprint as source truth.

## Codex Skill Repositories

Local paths:

```text
/Users/hoxide/.codex/skills
/Users/hoxide/mycodes/mathexpert/skills-codex
```

Use them for:

- skill file shape;
- trigger descriptions;
- progressive disclosure;
- reference file organization;
- reusable workflow design.

Relevant skills:

```text
skill-creator
writing-skills
mathexpert-md
math-research-md
lean4
blueprint-to-math-notes
problem-constructor
math-proof-review
```

The mdblueprint skills should be concise workflow guides, not long design essays.
