# Lean Repository Linking

`mdblueprint` can connect Markdown nodes to one or more Lean Git repositories. The
Markdown files remain the durable mathematical source; Lean links are mechanical
references used for checks, alignment review, and published source links.

## Repository Shape

A Lean repository is indexed from the directory named by `local_path`. Module names
come from `.lean` file paths under that root:

```text
path/to/example-lean/
  lakefile.lean
  Example/
    Basic.lean      -> module Example.Basic
    Advanced.lean   -> module Example.Advanced
```

Declarations are extracted from top-level Lean declarations and namespace scopes.
For example:

```lean
namespace Example

theorem basic_identity : True := True.intro

end Example
```

is indexed as declaration `Example.basic_identity`.

## Project Config

Put Lean repository config in the project config file, normally
`docs/knowledge/mdblueprint.yml`:

```yaml
site:
  title: Algebra Blueprint

lean:
  default_repository: core
  repositories:
    - id: core
      title: Example Lean Library
      local_path: ../example-lean
      web_url: https://github.com/example/example-lean
      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
      revision: auto
    - id: external
      title: External Lean Library
      local_path: /absolute/path/to/external-lean
      web_url: https://github.com/example/external-lean
      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
      revision: 0123456789abcdef
```

Config contract:

- `lean.repositories` is optional. If omitted, node Lean declarations are displayed
  as names but cannot become published source links.
- `id` is the stable repository id used by node frontmatter.
- `title` is the human-facing repository name shown in published Lean modals.
- `local_path` may be absolute or relative to the config file directory. It must
  exist and point at the root used to derive Lean module names.
- `web_url` is the repository browser URL without a required trailing slash.
- `source_url_template` is formatted with `{web_url}`, `{revision}`, `{path}`, and
  `{line}`. The path is the Lean file path relative to `local_path`.
- `revision` may be a literal commit, tag, or branch name. Use a commit hash for
  stable published links.
- `revision: auto` resolves to `git rev-parse HEAD` in `local_path` when the config
  is loaded. It requires `local_path` to be a Git repository.
- `default_repository` is optional. When present, any node without
  `lean.repository` uses this repository. The default id must appear in
  `lean.repositories`.
- `subdir` is optional. When the Lean source root is a subdirectory of the git
  repo (typical layout: a `lean/` directory inside the project), set
  `subdir: lean` so the `{path}` placeholder in `source_url_template` receives
  the prefixed path automatically. Leading and trailing slashes are normalised;
  empty value (the default) prepends nothing.
- `doc_url_template` is optional. When set, every resolved declaration gets a
  second `doc` link next to its source link in the rendered Lean modal. Useful
  for projects that publish doc-gen4 / mathlib4_docs output. Available
  placeholders: `{web_url}`, `{revision}`, `{module}` (dotted form),
  `{module_html}` (slash form), `{qualified_name}`. A malformed template
  degrades gracefully to no doc link rather than failing the publish.

### Example: project with a `lean/` subdirectory and hosted docs

```yaml
lean:
  default_repository: project
  repositories:
    - id: project
      title: ProjectLean
      local_path: ../../lean
      subdir: lean
      web_url: https://github.com/Org/Repo
      revision: main
      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
      doc_url_template: "https://org.github.io/Repo/docs/{module_html}.html#{qualified_name}"
```

A declaration `Foo.bar` at line 42 of `LeanProject/Foo.lean` renders with two
links:

- source: `https://github.com/Org/Repo/blob/main/lean/LeanProject/Foo.lean#L42`
- doc:    `https://org.github.io/Repo/docs/LeanProject/Foo.html#Foo.bar`

## Node Frontmatter

Nodes connect to Lean with a `lean` block:

```yaml
lean:
  repository: core
  modules:
    - Example.Basic
  declarations:
    - Example.basic_identity
```

Node contract:

- `lean.repository` is optional only when `lean.default_repository` is configured.
- `lean.modules` lists modules expected to exist in the selected repository.
- `lean.declarations` lists declarations expected to exist in the selected
  repository.
- Fully qualified declaration names are preferred.
- Short declaration names are accepted only when they match exactly one indexed
  declaration by suffix.
- The Lean block proves only mechanical linkage. Semantic alignment still requires
  alignment review evidence.

Lean metadata is optional for ordinary `admitted` Markdown nodes. Admission into
`docs/knowledge/nodes/` is based on mathematical verification evidence, not on
Lean coverage. Lean metadata is mandatory only for Lean-backed claims:

- `external-theorem` nodes, because their proof source is Lean;
- nodes with `status: formalized` or `status: proved`;
- nodes that set `verification.alignment`, because alignment is a semantic claim
  about a Markdown statement and a Lean declaration.

## Markdown-To-Lean Linking Workflow

First-time linking is Python-orchestrated and agent-agnostic. The deterministic
tools index configured Lean repositories, build a bounded candidate bundle, validate
agent output, and optionally apply only the `lean:` frontmatter block.

```bash
# Build a bounded candidate bundle for one node.
uv run python -m tools.knowledge.lean_link_candidates docs/knowledge --node-id <node-id>
# or, after install:
uv run mdblueprint-lean-link-candidates docs/knowledge --node-id <node-id>

# Validate an agent proposal and write a review report.
uv run python -m tools.knowledge.lean_linking docs/knowledge --proposal proposal.yml

# Apply a validated mechanical link to the node's lean block only.
uv run python -m tools.knowledge.lean_linking docs/knowledge --proposal proposal.yml --apply
```

Use `skills/mdblueprint-lean-linking/SKILL.md` for the agent step. Codex, Claude,
OpenCode, or a human reviewer should choose from the bounded candidates and return
`decision: link`, `no_match`, `ambiguous`, `needs_lean_generation`, or
`needs_human_decision`. The proposal may include `proposed_lean`, but it must not
set `verification.alignment`, `status: formalized`, or `status: proved`.

After mechanical linking, semantic alignment is a separate bounded workflow:

```bash
uv run python -m tools.knowledge.lean_alignment docs/knowledge \
  --node-id <node-id> \
  --declaration <Lean.Declaration>

uv run python -m tools.knowledge.lean_alignment docs/knowledge --report alignment.yml
```

The alignment verifier reads only the bundle from `tools.knowledge.lean_alignment`
and writes a review report. Updating `verification.alignment` or final status is a
later admission/referee decision, not part of mechanical linking.

## Private Repositories

Private Lean repositories use the same GitHub blob link shape as public
repositories. The only difference is access control: if the viewer is logged in to
GitHub and has permission for the private repository, the link opens; otherwise
GitHub denies access.

```yaml
lean:
  default_repository: core
  repositories:
    - id: core
      title: Private Lean Library
      local_path: ../private-lean
      web_url: https://github.com/example/private-lean
      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
      revision: auto
```

Security contract:

- The generated site contains ordinary GitHub URLs only. It must not contain
  tokens, secrets, signed URLs, or credential query parameters.
- `source_url_template` should be the same browser URL pattern used for public
  repositories, normally `{web_url}/blob/{revision}/{path}#L{line}`.
- Access is handled outside mdblueprint by GitHub permissions, deploy keys, or the
  local/CI checkout used to run the build.
- `revision: auto` resolves to the local Git `HEAD` commit, so private source links
  are stable without embedding credentials.
- Generated HTML, `graph.json`, topic subgraphs, and node payloads must not leak
  tokens or secrets.

## Checks

With project-level repository config, the normal check command indexes configured
repositories automatically:

```bash
uv run python -m tools.knowledge.check docs/knowledge
```

Use strict dirty-repository handling for release checks:

```bash
uv run python -m tools.knowledge.check docs/knowledge --strict-lean-git
```

Expected diagnostics:

- missing `lean.repository` when no default is configured: error;
- unknown `lean.repository`: error;
- missing module: warning for ordinary nodes, error for `external-theorem`;
- missing declaration: warning for ordinary nodes, error for `external-theorem`;
- ambiguous short declaration in configured mode: error;
- declaration body containing `sorry` or `admit`: warning;
- dirty configured Git repository: warning, or error with `--strict-lean-git`.

For one-off checks before a project config exists, use:

```bash
uv run python -m tools.knowledge.check docs/knowledge --lean-root path/to/lean/project
```

`--lean-root` uses a single unconfigured Lean root for mechanical prechecks. It does
not define repository ids, revisions, or source URL templates, and it is not used by
the publisher.

## Publishing

The publisher reads the same project config:

```bash
uv run python -m tools.knowledge.publish docs/knowledge /tmp/mdblueprint-site
```

When a node declaration resolves through a configured repository, node pages and graph
modals link the declaration to `source_url_template` and show repository title,
short revision, and module metadata.

If a configured declaration cannot be resolved, the generated site shows the
declaration name with an `Unresolved` marker and does not create a broken source link.
Run `tools.knowledge.check` to get the corresponding diagnostic before publishing a
release site.

## Generic Fixture Pattern

A minimal non-domain-specific fixture can use this shape:

```text
fixtures/example_lean/
  Example/
    Basic.lean

fixtures/example_knowledge/
  mdblueprint.yml
  nodes/example/basic_identity.md
```

The knowledge config points `lean.repositories[0].local_path` at
`fixtures/example_lean`, and the node frontmatter uses:

```yaml
lean:
  repository: core
  modules:
    - Example.Basic
  declarations:
    - Example.basic_identity
```

This is the recommended shape for tests and examples: small Lean files, generic
module names, and no assumption that a particular mathematical domain is the default.

## Reverse Links (`Blueprint:` markers)

The Markdown side declares Lean references with `lean.declarations`. That is
the **forward** edge MD → Lean. mdblueprint also reads optional **reverse**
edges Lean → MD when Lean files use a `Blueprint:` marker in their docstrings.
Having both edges lets the index detect drift in either direction: a renamed
Lean declaration loses its forward edge but keeps its reverse marker, and vice
versa.

### Marker syntax

There are two granularities, both optional and back-compatible. A project can
adopt them incrementally.

**Module level** (in the file's `/-! ... -/` header):

```lean
/-!
# G_m

...

## Blueprint

`linear_algebraic_groups.multiplicative_group_scheme`
`reductive_structure.algebraic_tori`
-/
```

Every declaration in the file inherits these node ids. The inline form
`## Blueprint: foo.bar` also works for a single id.

**Declaration level** (in the `/-- ... -/` docstring above a specific
declaration):

```lean
/-- Multiplicative group scheme over `S`.

Blueprint: linear_algebraic_groups.multiplicative_group_scheme
-/
noncomputable def multiplicativeGroup : ... := ...
```

A single line `Blueprint: <node_id>[, <node_id>...]`. Per-declaration markers
take priority and are merged (union) with module-level markers.

doc-gen4 and mathlib4_docs render docstrings unchanged, so readers of the
Lean documentation see the back-reference inline.

### Cross-check CLI

```bash
uv run python -m tools.knowledge.lean_reverse_check docs/knowledge
```

Output is a list of per-edge diagnostics in four categories:

| Category         | Meaning                                          | Severity |
|------------------|--------------------------------------------------|----------|
| `ok`             | both directions agree                            | info     |
| `md_only`        | MD points at decl; decl has no Blueprint marker  | info     |
| `lean_only`      | Lean claims node; node's `lean.declarations` lacks decl | warning  |
| `cross_mismatch` | both maps name the decl, sets disagree           | error    |

By default only issues are printed (`--show all` includes `ok` rows;
`--show errors` shows only `cross_mismatch`). The CLI exits non-zero when any
cross-mismatch is present (exit 2), making it suitable as a CI gate. Pass
`--strict` to also fail on `lean_only` warnings (exit 1).

### Recommended workflow

1. Adopt module-level markers when formalising a new file. One line per
   blueprint node the module backs; doc-gen4 readers see them for free.
2. Add per-declaration markers when one module backs multiple blueprint
   nodes and you need finer granularity.
3. Run `lean_reverse_check` in CI alongside `tools.knowledge.check`.
4. Treat `lean_only` as a signal that the MD side might want a
   `lean.declarations` entry; treat `cross_mismatch` as a hard error
   (a real Lean rename usually surfaces here).

## Rendered Lean Modal

The published node page exposes a `L∃∀N` button that opens a modal with every
resolved declaration and module. For each entry mdblueprint surfaces, when
available:

- The Lean **kind** (`def`, `theorem`, `lemma`, `instance`, `structure`, ...) as
  a small badge.
- The qualified declaration name as a clickable source link.
- An optional second `doc` link when `doc_url_template` is set.
- The repository title, short revision, and module name.
- The `/-- … -/` docstring above the declaration, when present.
- A multi-line signature snippet (first line through the first `:=`, or the
  declaration header for `structure` / `class`).
- A `sorry/admit` badge if the declaration body contains a placeholder.

For `lean.modules`, each module is rendered as a link to **line 1** of the file
backing that module.

For unresolved entries, mdblueprint adds "Did you mean: a, b, c?" suggestions
ranked by:

1. Suffix match on the last segment (e.g. `bar` → `Foo.Namespace.bar`).
2. Module match (e.g. asking for a declaration name that is in fact a module
   becomes `(module) Foo.Bar`).
3. Token overlap on the lowercased / camelCase-split tokens.

The same suggestions appear in `tools.knowledge.check` diagnostics:

```
[WARNING] foo.bar (foo.bar): Lean declaration not found in repository 'main':
          'IsBestResponser'; suggestions: StrategicGame.IsBestResponse, ...
```

## Troubleshooting

- **"Lean declaration not found" but it exists.** Use the suggestion from
  the diagnostic. If the entry is a module name, move it from
  `lean.declarations` to `lean.modules`. Use the fully qualified name in
  `lean.declarations`.
- **Source URLs point to a nonexistent path.** Your Lean source root is a
  subdirectory of the git repo. Set `subdir: <dir>` on the repository config
  instead of hardcoding the prefix in `source_url_template`.
- **`Lean repository has uncommitted or untracked files` warning.** The
  configured Lean repo has working-tree changes; with `revision: auto` the
  generated URLs would point at a sha you didn't push. Commit (or push) and
  re-run, or pass `--strict-lean-git` to make this fatal in CI.
- **Branch revision shows oddly in the modal.** As of the fix for branch /
  tag revisions, `short_revision` only truncates 7-40-char hex SHAs; branch
  names like `release/v0.1` or tag names like `v1.2.3-rc4` are shown as-is.
- **Doc URL doesn't appear.** Check that `doc_url_template` is non-empty
  and uses only `{web_url}`, `{revision}`, `{module}`, `{module_html}`,
  `{qualified_name}`. Bad templates degrade silently to no doc link rather
  than crashing publish.
