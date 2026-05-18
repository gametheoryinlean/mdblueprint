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
