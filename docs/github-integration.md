# GitHub Integration

This document records the GitHub Actions publishing pattern currently used by
GameTheoryLib/EconCSLib. The pattern is reusable for any Lean or mathematical
library that keeps mdblueprint source files in its main repository and wants
GitHub Actions to publish a generated blueprint site after source changes.

## Publishing Model

Use three repositories or checkouts with separate responsibilities:

- main project repository: owns Lean code, `docs/knowledge`, and
  `docs/knowledge/mdblueprint.yml`;
- mdblueprint repository: owns the checker, publisher, renderer, templates, and
  command-line tools;
- blueprint publishing repository: owns only generated static-site files on a
  Pages branch such as `gh-pages`.

The main project repository is the source of truth. Generated HTML, graph JSON,
topic subgraphs, and node payloads are build artifacts and should not be
hand-edited or committed back into the source tree.

On each relevant update to the main project, the action checks out the project,
checks out mdblueprint, validates `docs/knowledge`, publishes into `_site`,
verifies the generated artifacts and rendered pages, then copies `_site` into
the publishing repository branch.

## Source Repository Requirements

The source repository should contain:

```text
docs/knowledge/
  mdblueprint.yml
  nodes/**/*.md
  staged/**/*.md
  reviews/**/*.md
  requests/**/*.md
```

For Lean source links, configure the local repository in
`docs/knowledge/mdblueprint.yml`:

```yaml
site:
  title: Example Library Blueprint
  short_title: Example

lean:
  default_repository: core
  repositories:
    - id: core
      title: Example Library
      local_path: ../..
      web_url: https://github.com/example/example-library
      source_url_template: "{web_url}/blob/{revision}/{path}#L{line}"
      revision: auto
```

Here `local_path: ../..` is relative to `docs/knowledge/mdblueprint.yml`, so it
points at the root of the checked-out source repository. `revision: auto`
resolves to the source commit that triggered the workflow, giving published Lean
links stable commit-based URLs.

Private Lean source repositories use the same `web_url` and
`source_url_template` shape. The generated link is still an ordinary GitHub blob
URL; it opens only for viewers who are logged in and have the necessary GitHub
permissions. Do not put tokens, secrets, signed URLs, or credential query
parameters into `web_url` or `source_url_template`. CI credentials are only for
checking out and indexing the repository during the build, not for generated HTML,
graph JSON, topic subgraphs, or node payloads.

## Trigger Rules

The GameTheoryLib workflow runs on manual dispatch and on pushes to `main` that
can change the published site:

- `docs/knowledge/**`, because Markdown node content is the blueprint source;
- Lean files and root import files, because Lean declaration links and
  placeholder diagnostics can change;
- `lean-toolchain`, `lakefile.toml`, and `lake-manifest.json`, because the Lean
  project shape and module resolution can change;
- README, agent instructions, or other documented project metadata that should
  stay synchronized with the publication contract;
- the workflow file itself.

Use a concurrency group keyed by the ref and `cancel-in-progress: true` so a new
push to `main` replaces an older in-flight publication for the same branch.

## Required Secrets

The separate-repository publishing pattern uses deploy keys:

- `MDBLUEPRINT_DEPLOY_KEY`: read access to the mdblueprint repository when it is
  private or accessed over SSH;
- `BLUEPRINT_DEPLOY_KEY`: write access to the blueprint publishing repository.

If the Lean source repository itself is private, give the workflow read access
through normal GitHub permissions or a deploy key during checkout. That access is
not copied into the published site. The published source links remain ordinary
GitHub URLs and rely on each viewer's own GitHub permissions.

Keep workflow permissions minimal, for example:

```yaml
permissions:
  contents: read
```

The write permission comes from the publishing deploy key, not from broad
`GITHUB_TOKEN` permissions. If mdblueprint is public, the checkout step can use
HTTPS and the `MDBLUEPRINT_DEPLOY_KEY` secret can be omitted.

## Workflow Steps

A reusable workflow follows this sequence:

1. Check out the main project repository with `actions/checkout`.
2. Configure SSH for mdblueprint if the tooling repository is private.
3. Clone mdblueprint at `MDBLUEPRINT_REF`, usually `main` for latest tooling or
   a tag/commit for reproducible releases.
4. Log both the source repository commit and mdblueprint commit.
5. Install mdblueprint with browser extras:

   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -e "_mdblueprint[browser]"
   python3 -m playwright install --with-deps chromium
   ```

6. Run the structural and Lean-link check:

   ```bash
   mdblueprint-check docs/knowledge --lean-root .
   ```

   The `--lean-root .` argument lets the checker index declarations in the
   checked-out source repository. Projects with fully configured
   `lean.repositories` still use the project config for source URLs.

7. Publish the site outside the source tree:

   ```bash
   rm -rf _site
   mdblueprint-publish docs/knowledge _site
   touch _site/.nojekyll
   ```

8. Verify the expected machine artifacts exist before treating publishing as
   successful:

   ```bash
   test -f _site/graph_topics.json
   test -f _site/dep_graph_document.html
   test -f _site/graph.html
   test "$(find _site/subgraphs/topics -name '*.json' -type f | wc -l | tr -d ' ')" -gt 0
   test "$(find _site/node_payloads -name '*.json' -type f | wc -l | tr -d ' ')" -gt 0
   ```

9. Run browser render QA:

   ```bash
   mdblueprint-render-check _site --timeout-ms 30000
   ```

10. Upload `_site` with `actions/upload-artifact` so failed or successful runs
    can be inspected from the Actions UI.
11. Configure SSH for the blueprint publishing repository.
12. Clone the target branch if it exists, or create it as an orphan branch.
13. Synchronize generated files with deletion of stale artifacts:

    ```bash
    rsync -a --delete --exclude .git _site/ "$publish_dir"/
    ```

14. Commit only when there are actual site changes. Include the source commit in
    the generated commit message and push the publishing branch.

This makes publication idempotent: a workflow run with no generated diff exits
without creating an empty commit.

## Workflow Template

Adapt the repository names, branch names, trigger paths, and optional
`MDBLUEPRINT_REF` pin:

```yaml
name: Build and Publish Blueprint

on:
  push:
    branches: [main]
    paths:
      - "docs/knowledge/**"
      - "**/*.lean"
      - "lean-toolchain"
      - "lakefile.toml"
      - "lake-manifest.json"
      - ".github/workflows/blueprint.yml"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: blueprint-${{ github.ref }}
  cancel-in-progress: true

jobs:
  build_blueprint:
    runs-on: ubuntu-latest
    env:
      BLUEPRINT_REPOSITORY: git@github.com:example/blueprint.git
      BLUEPRINT_BRANCH: gh-pages
      MDBLUEPRINT_REF: main
    steps:
      - name: Checkout source repository
        uses: actions/checkout@v4

      - name: Configure mdblueprint checkout key
        env:
          MDBLUEPRINT_DEPLOY_KEY: ${{ secrets.MDBLUEPRINT_DEPLOY_KEY }}
        run: |
          test -n "$MDBLUEPRINT_DEPLOY_KEY" || {
            echo "MDBLUEPRINT_DEPLOY_KEY secret is required to checkout mdblueprint."
            exit 1
          }
          install -m 700 -d ~/.ssh
          printf '%s\n' "$MDBLUEPRINT_DEPLOY_KEY" > ~/.ssh/mdblueprint_deploy_key
          chmod 600 ~/.ssh/mdblueprint_deploy_key
          ssh-keyscan -H github.com >> ~/.ssh/known_hosts

      - name: Checkout mdblueprint
        env:
          GIT_SSH_COMMAND: ssh -i ~/.ssh/mdblueprint_deploy_key -o IdentitiesOnly=yes
        run: |
          git clone --depth 1 --branch "$MDBLUEPRINT_REF" \
            git@github.com:example/mdblueprint.git _mdblueprint

      - name: Log source revisions
        run: |
          echo "Source revision:"
          git rev-parse HEAD
          git log -1 --oneline
          echo "mdblueprint revision:"
          git -C _mdblueprint rev-parse HEAD
          git -C _mdblueprint log -1 --oneline

      - name: Install mdblueprint
        run: |
          python3 -m pip install --upgrade pip
          python3 -m pip install -e "_mdblueprint[browser]"
          python3 -m playwright install --with-deps chromium

      - name: Check mdblueprint knowledge graph
        run: mdblueprint-check docs/knowledge --lean-root .

      - name: Publish mdblueprint site
        run: |
          rm -rf _site
          mdblueprint-publish docs/knowledge _site
          touch _site/.nojekyll

      - name: Verify graph artifacts
        run: |
          test -f _site/graph_topics.json
          test -f _site/dep_graph_document.html
          test -f _site/graph.html
          topic_subgraphs="$(find _site/subgraphs/topics -name '*.json' -type f | wc -l | tr -d ' ')"
          node_payloads="$(find _site/node_payloads -name '*.json' -type f | wc -l | tr -d ' ')"
          test "$topic_subgraphs" -gt 0
          test "$node_payloads" -gt 0
          echo "Topic subgraphs: $topic_subgraphs"
          echo "Node payloads: $node_payloads"

      - name: Check rendered blueprint pages
        run: mdblueprint-render-check _site --timeout-ms 30000

      - name: Upload blueprint artifact
        uses: actions/upload-artifact@v4
        with:
          name: blueprint-site
          path: _site

      - name: Configure blueprint deploy key
        env:
          BLUEPRINT_DEPLOY_KEY: ${{ secrets.BLUEPRINT_DEPLOY_KEY }}
        run: |
          test -n "$BLUEPRINT_DEPLOY_KEY" || {
            echo "BLUEPRINT_DEPLOY_KEY secret is required to publish the blueprint."
            exit 1
          }
          install -m 700 -d ~/.ssh
          printf '%s\n' "$BLUEPRINT_DEPLOY_KEY" > ~/.ssh/blueprint_deploy_key
          chmod 600 ~/.ssh/blueprint_deploy_key
          ssh-keyscan -H github.com >> ~/.ssh/known_hosts

      - name: Publish to blueprint repository
        env:
          GIT_SSH_COMMAND: ssh -i ~/.ssh/blueprint_deploy_key -o IdentitiesOnly=yes
        run: |
          set -euo pipefail
          publish_dir="$(mktemp -d)"

          if git ls-remote --exit-code --heads "$BLUEPRINT_REPOSITORY" "$BLUEPRINT_BRANCH" >/dev/null; then
            git clone --depth 1 --branch "$BLUEPRINT_BRANCH" "$BLUEPRINT_REPOSITORY" "$publish_dir"
          else
            git clone --depth 1 "$BLUEPRINT_REPOSITORY" "$publish_dir"
            (
              cd "$publish_dir"
              git checkout --orphan "$BLUEPRINT_BRANCH"
              git rm -rf . >/dev/null 2>&1 || true
            )
          fi

          rsync -a --delete --exclude .git _site/ "$publish_dir"/

          cd "$publish_dir"
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A

          if git diff --cached --quiet; then
            echo "No blueprint changes to publish."
            exit 0
          fi

          git commit \
            -m "Build blueprint from ${GITHUB_REPOSITORY} ${GITHUB_SHA}" \
            -m "Source: https://github.com/${GITHUB_REPOSITORY}/commit/${GITHUB_SHA}"
          git push origin "$BLUEPRINT_BRANCH"
```

## Adapting To Other Projects

Project-specific values:

- `BLUEPRINT_REPOSITORY`: the repository that hosts generated static files;
- `BLUEPRINT_BRANCH`: the GitHub Pages branch, usually `gh-pages`;
- `MDBLUEPRINT_REF`: `main` for latest tooling, or a pinned tag/commit for
  reproducible publication;
- source trigger paths: narrow them to files that can affect the blueprint;
- `docs/knowledge/mdblueprint.yml`: set `site`, `topics`, `math`, `graph`, and
  `lean.repositories` for the project.

When using a separate target repository, keep that repository only for generated
static artifacts. If the project wants to publish from the same repository
instead, replace the final deploy-key push with the repository's GitHub Pages
deployment mechanism, but keep the same check, publish, artifact verification,
and render-check steps.

## Operational Rules

- Do not publish until `mdblueprint-check` exits successfully.
- Treat browser render-check failures as release blockers unless they are
  explicitly documented as external service or asset failures.
- Keep generated files out of the source repository.
- Use `rsync --delete` or equivalent so removed nodes disappear from the
  published site.
- Keep source and mdblueprint revisions in the workflow log.
- Include the source commit URL in generated publishing commits.
- Pin `MDBLUEPRINT_REF` when a project needs reproducible releases; use `main`
  when the project intentionally tracks the latest mdblueprint publisher.
