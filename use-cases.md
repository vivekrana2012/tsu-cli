# Use Cases

Practical workflows showing how to use `tsu` in different scenarios.

---

## 1. Generate a Tech Document (Default)

The most common workflow — analyze a codebase and produce a technical overview,
then publish it to Confluence.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Developer Machine                            │
│                                                                     │
│  ┌───────────┐     ┌──────────────┐     ┌───────────┐              │
│  │  tsu init │────▶│ tsu generate │────▶│ tsu push  │──┐           │
│  └───────────┘     └──────────────┘     └───────────┘  │           │
│        │                  │                             │           │
│        ▼                  ▼                             │           │
│   .tsu/                .tsu/                            │           │
│   ├─ config.json       document.md                     │           │
│   ├─ confluence.json                                   │           │
│   └─ generate.md                                       │           │
│                                                        │           │
└────────────────────────────────────────────────────────┼───────────┘
                                                         │
                                                         ▼
                                                  ┌─────────────┐
                                                  │  Confluence  │
                                                  │  Tech Page   │
                                                  └─────────────┘
```

```bash
cd /path/to/your/project
tsu init                    # set up model, Confluence target, prompt template
tsu generate                # analyze codebase → .tsu/document.md
tsu push                    # upload to Confluence
```

---

## 2. Multiple Document Profiles

Use profiles to generate different types of documentation from the same
codebase — each with its own prompt template, output file, and Confluence page.

```
                           ┌──────────────────┐
                     ┌────▶│  generate.md     │──▶ document.md     ──▶ Confluence: Tech Overview
                     │     └──────────────────┘
                     │
┌───────────┐        │     ┌──────────────────┐
│  Codebase │────────┼────▶│  generate-api.md │──▶ document-api.md ──▶ Confluence: API Spec
│           │        │     └──────────────────┘
└───────────┘        │
                     │     ┌──────────────────┐
                     └────▶│  generate-biz.md │──▶ document-biz.md ──▶ Confluence: Business Rules
                           └──────────────────┘
```

### Example: API specification

```bash
tsu init --profile api
# During init, set a page title like "MyProject - API Reference"
# Edit .tsu/generate-api.md to focus on endpoints, request/response schemas, auth

tsu generate --profile api
tsu push --profile api
```

### Example: Business rules / filter & mapping doc

```bash
tsu init --profile biz
# Edit .tsu/generate-biz.md with instructions like:
#   "Document all business rules, validation logic, data transformations,
#    and field-mapping tables found in the codebase."

tsu generate --profile biz
tsu push --profile biz
```

### Listing all profiles

```bash
tsu list-profiles
# Profile    Prompt File          Page Title               Page ID
# tech       generate.md          MyProject - Tech Docs    12345
# api        generate-api.md      MyProject - API Spec     12346
# biz        generate-biz.md      MyProject - Biz Rules    12347
```

---

## 3. Offline Mode (No Confluence)

Generate documentation as a local markdown file without any Confluence
integration — useful for markdown-only projects, local previews, or when
Confluence credentials are unavailable.

```
┌───────────┐     ┌────────────────────────┐     ┌──────────────────┐
│  tsu init │────▶│ tsu generate --offline │────▶│ .tsu/document.md │
└───────────┘     └────────────────────────┘     └──────────────────┘
      │
      ▼
 Skip Confluence
 URL during init
 (leave blank)
```

```bash
cd /path/to/your/project
tsu init                       # leave parent page URL blank when prompted
tsu generate --offline         # skip Confluence sync, generate from codebase only
# .tsu/document.md is ready — commit it, preview it, share it
```

You can also use `--offline` when Confluence is configured but you want a
clean regeneration without pulling the remote page first.

---

## 4. Org-Wide Standard Templates

Distribute a shared `generate.md` template across teams so every project
produces documentation with the same structure and level of detail.

```
┌───────────────────────────────┐
│  Shared repo / artifact       │
│  └─ templates/                │
│     ├─ generate-standard.md   │     ┌──────────────────┐
│     ├─ generate-api.md        │────▶│  Team A project  │
│     └─ generate-security.md   │     │  .tsu/generate.md│
└───────────────────────────────┘     └──────────────────┘
              │
              │                       ┌──────────────────┐
              └──────────────────────▶│  Team B project  │
                                      │  .tsu/generate.md│
                                      └──────────────────┘
```

### Setup

1. Create a shared repository or artifact containing your organisation's
   prompt templates.
2. After running `tsu init`, replace the default `.tsu/generate.md` with your
   standard template:
   ```bash
   tsu init
   cp /path/to/templates/generate-standard.md .tsu/generate.md
   ```
3. Commit `.tsu/generate.md` to the project repo so the template travels with
   the codebase.
4. Re-running `tsu init` will **not** overwrite an existing template, so
   manual edits and org templates are preserved.

### Combining with profiles

```bash
tsu init --profile api
cp /path/to/templates/generate-api.md .tsu/generate-api.md

tsu init --profile security
cp /path/to/templates/generate-security.md .tsu/generate-security.md
```

---

## 5. CI/CD Pipeline Integration

Run `tsu generate` and `tsu push` in an automated pipeline. The `page_id`
created during local `tsu init` ensures the pipeline updates the existing
page instead of creating duplicates.

```
┌──────────────────────────────────────────────────────────────────┐
│                       CI/CD Pipeline                              │
│                                                                   │
│  ┌────────────────┐     ┌──────────────┐     ┌───────────┐       │
│  │  Checkout repo │────▶│ tsu generate │────▶│ tsu push  │───┐   │
│  └────────────────┘     └──────────────┘     └───────────┘   │   │
│                                │                              │   │
│                                ▼                              │   │
│                          Uses page_id                         │   │
│                          from committed                       │   │
│                          .tsu/confluence.json                 │   │
│                                                               │   │
│  Environment:                                                 │   │
│    CONFLUENCE_USER=bot@company.com                             │   │
│    CONFLUENCE_TOKEN=****                                       │   │
└───────────────────────────────────────────────────────────────┼───┘
                                                                │
                                                                ▼
                                                         ┌─────────────┐
                                                         │  Confluence  │
                                                         │  (updated)   │
                                                         └─────────────┘
```

### Setup

1. Run `tsu init` locally — this creates the Confluence page and saves the
   `page_id` in `.tsu/confluence.json`.
2. Commit the `.tsu/` directory to version control.
3. Set `CONFLUENCE_USER` and `CONFLUENCE_TOKEN` as pipeline secrets.

### Example pipeline step

```bash
pip install tsu-cli
tsu generate --offline    # or without --offline to sync first
tsu push
```

The `--offline` flag is recommended in CI to avoid pulling content during
generation, keeping builds deterministic.

---

## 6. Syncing with Manual Confluence Edits

When someone edits the Confluence page directly (e.g. adds a "Known Issues"
section by hand), `tsu generate` preserves those edits automatically.

```
┌────────────┐                               ┌─────────────┐
│  Developer │──── edits page manually ─────▶│  Confluence  │
└────────────┘                               └──────┬──────┘
                                                    │
                ┌───────────────────────────────────┘
                │  tsu generate pulls current page
                ▼
       ┌──────────────┐     ┌──────────────────────────────────┐
       │ Remote page   │───▶│ LLM receives remote + codebase   │
       │ (with manual  │    │ ─ Updates codebase-driven sections│
       │  edits)       │    │ ─ Preserves manual additions      │
       └──────────────┘     └──────────────┬───────────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  tsu push   │──▶ Confluence (merged)
                                    └─────────────┘
```

```bash
# Someone adds a "Known Issues" section on the Confluence page directly
# Then you regenerate:
tsu generate          # pulls remote page first, LLM preserves manual sections
tsu push              # uploads merged result
```

To skip the sync and regenerate fresh from the codebase only:

```bash
tsu generate --offline
```

---

## 7. Pull a Confluence Page for Local Review

Fetch the current remote page as local markdown — useful for reviewing
changes, running diffs, or editing locally before pushing back.

```
┌─────────────┐     ┌──────────┐     ┌──────────────────┐
│  Confluence  │────▶│ tsu pull │────▶│ .tsu/document.md │
└─────────────┘     └──────────┘     └──────────────────┘
                                            │
                                     Edit locally or
                                     diff with git
                                            │
                                            ▼
                                     ┌───────────┐     ┌─────────────┐
                                     │ tsu push  │────▶│  Confluence  │
                                     └───────────┘     └─────────────┘
```

```bash
tsu pull                    # fetch remote page → .tsu/document.md
git diff .tsu/document.md   # see what changed remotely
# edit .tsu/document.md if needed
tsu push                    # push updated version back
```

---

## 8. Doc Drift Detection in CI

Catch outdated documentation automatically. Run `tsu generate` in CI and
check whether the output differs from what's committed — if it does, someone
changed code without updating docs.

```
┌────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  Checkout repo │────▶│ tsu generate --offline│────▶│ git diff --exit-code │
└────────────────┘     └──────────────────────┘     │ .tsu/document.md     │
                                                     └──────────┬───────────┘
                                                                │
                                                     ┌──────────┴───────────┐
                                                     │                      │
                                                     ▼                      ▼
                                               No changes             Changes found
                                               ──▶ ✅ Pass            ──▶ ❌ Fail
```

### GitHub Actions example

```yaml
- name: Check doc freshness
  run: |
    pip install tsu-cli
    tsu generate --offline
    git diff --exit-code .tsu/document.md || {
      echo "::error::Documentation is out of date. Run 'tsu generate' locally and commit."
      exit 1
    }
```

---

## 9. PR-Driven Doc Review

Generate docs on a feature branch so reviewers see how the architecture or
API surface changed — right alongside the code diff.

```
┌──────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ feature branch   │────▶│ tsu generate │────▶│ git commit   │────▶│ Open PR      │
│ (code changes)   │     │ --offline    │     │ .tsu/doc.md  │     │              │
└──────────────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                         │
                                                                         ▼
                                                                  ┌──────────────┐
                                                                  │ PR diff shows│
                                                                  │ code + doc   │
                                                                  │ changes      │
                                                                  └──────────────┘
```

```bash
git checkout -b feat/new-api
# ... make code changes ...
tsu generate --offline
git add .tsu/document.md
git commit -m "docs: update for new API endpoints"
git push origin feat/new-api
# PR reviewers see doc changes in the diff
```

This also works well when combined with drift detection (use case 8) — the
CI check ensures developers don't forget to regenerate before opening a PR.

---

## 10. Merge Conflict Resolution via Regeneration

When `git merge` produces conflicts in `.tsu/document.md`, don't resolve
them manually — regenerate the document from the merged codebase. The LLM
re-analyzes everything and produces a clean result.

```
┌──────────┐     ┌──────────┐
│  main    │     │ feature  │
│ doc v1   │     │ doc v2   │
└────┬─────┘     └────┬─────┘
     │                │
     └───────┬────────┘
             │ git merge
             ▼
      ┌──────────────┐
      │  CONFLICT in │
      │  document.md │
      └──────┬───────┘
             │
             ▼
      ┌──────────────────┐     ┌──────────────┐
      │ tsu generate     │────▶│ Clean doc v3 │
      │ (from merged src)│     │ (no conflict)│
      └──────────────────┘     └──────────────┘
```

```bash
git merge feature/new-api
# CONFLICT in .tsu/document.md

# instead of resolving manually:
tsu generate --offline        # regenerate from merged codebase
git add .tsu/document.md
git commit                    # complete the merge
```

This works because the document is generated from source code, not
hand-written — the merged codebase is the source of truth.

---

## 11. Release-Tagged Doc Snapshots

Generate a documentation snapshot for each release. Use a dedicated profile
so each version gets its own Confluence page — building a historical record
of how the system evolved.

```
┌────────────────────┐     ┌──────────────────┐     ┌───────────┐
│  git tag v1.2.0    │────▶│ tsu generate     │────▶│ tsu push  │
│                    │     │ --profile release │     │ --profile │
└────────────────────┘     └──────────────────┘     │  release  │
                                                     └─────┬─────┘
                                                           │
         ┌─────────────────────────────────────────────────┘
         ▼
  Confluence
  ├─ MyProject v1.0.0   (page_id: 1001)
  ├─ MyProject v1.1.0   (page_id: 1002)
  └─ MyProject v1.2.0   (page_id: 1003)  ◀── new
```

```bash
# one-time setup
tsu init --profile release
# set page title to "MyProject v1.2.0" during init

# on each release
git tag v1.2.0
tsu generate --profile release --extra "Document version 1.2.0 changes"
tsu push --profile release

# for the next release, re-init with a new page title
tsu init --profile release
# set page title to "MyProject v1.3.0"
```

### Automating in CI

```yaml
on:
  push:
    tags: ["v*"]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          pip install tsu-cli
          tsu generate --profile release --extra "Release ${{ github.ref_name }}"
          tsu push --profile release
```

---

## 12. Git Hooks for Auto-Generation

Use git hooks to regenerate docs automatically when code changes land —
ensuring documentation is always current without manual intervention.

```
┌───────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  git pull     │────▶│ post-merge hook       │────▶│ .tsu/document.md │
│  git merge    │     │ runs tsu generate     │     │ (updated)        │
└───────────────┘     └──────────────────────┘     └──────────────────┘

┌───────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  git push     │────▶│ pre-push hook         │────▶│ Fail if docs are │
│               │     │ checks doc freshness  │     │ out of date      │
└───────────────┘     └──────────────────────┘     └──────────────────┘
```

### post-merge: regenerate after pulling changes

```bash
# .git/hooks/post-merge
#!/bin/sh
if [ -d ".tsu" ]; then
  echo "Regenerating documentation..."
  tsu generate --offline
  git add .tsu/document*.md
  echo "Docs updated — review and commit when ready."
fi
```

### pre-push: block pushes with stale docs

```bash
# .git/hooks/pre-push
#!/bin/sh
if [ -d ".tsu" ]; then
  tsu generate --offline 2>/dev/null
  if ! git diff --quiet .tsu/document*.md; then
    echo "ERROR: Documentation is out of date."
    echo "Run 'tsu generate' and commit before pushing."
    exit 1
  fi
fi
```

---

## 13. Feature Branch Documentation

Create a temporary documentation profile for a feature branch. The generated
Confluence page serves as a living design doc while the feature is being
built, and becomes the handoff artifact after merge.

```
┌──────────────────┐
│  git checkout    │
│  -b feat/payments│
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  tsu init        │────▶│  tsu generate    │────▶│  tsu push   │
│  --profile       │     │  --profile       │     │  --profile  │
│  feat-payments   │     │  feat-payments   │     │ feat-payments│
└──────────────────┘     └──────────────────┘     └──────┬──────┘
                                                         │
  Edit .tsu/generate-feat-payments.md                    ▼
  to focus on:                                    ┌─────────────┐
  • Payment flow design                          │ Confluence   │
  • Integration points                           │ "Payments    │
  • Data model changes                           │  Feature"    │
                                                  └─────────────┘
         After merge:
         ┌──────────────────────────────────┐
         │ Page stays as historical record  │
         │ Remove profile files if desired  │
         └──────────────────────────────────┘
```

```bash
# start the feature
git checkout -b feat/payments
tsu init --profile feat-payments
# edit .tsu/generate-feat-payments.md:
#   "Focus on the payment processing flow, integration points,
#    data model changes, and error handling."

# iterate while building
tsu generate --profile feat-payments
tsu push --profile feat-payments

# after merge — the Confluence page remains as documentation
git checkout main
git merge feat/payments
# optionally clean up profile files
rm .tsu/generate-feat-payments.md .tsu/confluence-feat-payments.json
```
