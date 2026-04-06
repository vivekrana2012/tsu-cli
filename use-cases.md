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
tsu init                    # set up model, Confluence target, prompt file
tsu generate                # analyze codebase → .tsu/document.md
tsu push                    # upload to Confluence
```

---

## 2. Multiple Document Profiles

Use profiles to generate different types of documentation from the same
codebase — each with its own prompt file, output file, and Confluence page.

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

## 4. Org-Wide Standard Profiles

Distribute a shared `generate.md` prompt file across teams so every project
produces documentation with the same structure and level of detail.

```
┌───────────────────────────────┐
│  Shared repo / artifact       │
│  └─ profiles/                 │
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
   prompt files.
2. After running `tsu init`, replace the default `.tsu/generate.md` with your
   standard profile:
   ```bash
   tsu init
   cp /path/to/profiles/generate-standard.md .tsu/generate.md
   ```
3. Commit `.tsu/generate.md` to the project repo so the prompt file travels with
   the codebase.
4. Re-running `tsu init` will **not** overwrite an existing prompt file, so
   manual edits and org profiles are preserved.

### Combining with profiles

```bash
tsu init --profile api
cp /path/to/profiles/generate-api.md .tsu/generate-api.md

tsu init --profile security
cp /path/to/profiles/generate-security.md .tsu/generate-security.md
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

## 8. Cross-Repo Doc Consumption (QA / Standalone Pull)

Pull a Confluence page directly by URL — no `tsu init` required. Useful when
the consumer (e.g. a QA engineer) works in a separate repository and just
needs the dev team's documentation as a local markdown file.

```
┌──────────────────────────────────────────────────────────────────┐
│                     Dev Team Repo                                │
│                                                                  │
│  tsu init → tsu generate → tsu push ──┐                         │
│                                        │                         │
└────────────────────────────────────────┼─────────────────────────┘
                                         │
                                         ▼
                                  ┌─────────────┐
                                  │  Confluence  │
                                  │  Tech Page   │
                                  │  (page 12345)│
                                  └──────┬──────┘
                                         │
┌────────────────────────────────────────┼─────────────────────────┐
│                     QA / Consumer Repo │                         │
│                                        │                         │
│  tsu pull --url <page_url> ◀───────────┘                        │
│       │                                                          │
│       ▼                                                          │
│  .tsu/document-12345.md                                          │
│                                                                  │
│  • No tsu init needed                                            │
│  • No config.json, no prompt files                               │
│  • Just the page content as markdown                             │
└──────────────────────────────────────────────────────────────────┘
```

```bash
# In the QA repo (no .tsu/ directory, no tsu init)
tsu auth set                # one-time: store Confluence credentials
tsu pull --url https://acme.atlassian.net/wiki/spaces/DEV/pages/12345/Tech+Overview

# Use the doc to inform test cases, review specs, etc.
cat .tsu/document-12345.md
```

---

## 9. Doc Drift Detection in CI

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

## 10. PR-Driven Doc Review

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

## 11. Merge Conflict Resolution via Regeneration

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

## 12. Release-Tagged Doc Snapshots

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

## 13. Git Hooks for Auto-Generation

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

## 14. Feature Branch Documentation

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

---

## 15. Pre-Push Sanity Check with `tsu diff`

Before pushing updated documentation to Confluence, run `tsu diff` to see
what the current doc is missing relative to recent code changes. Decide
whether to push as-is or regenerate first — no more guessing.

```
┌──────────────┐     ┌──────────┐     ┌─────────────────────────────┐
│  Code changes│────▶│ tsu diff │────▶│ .tsu/diff.md                │
│  (committed) │     └──────────┘     │ ┌─────────────────────────┐ │
└──────────────┘                      │ │ What's Stale            │ │
                                      │ │ What's New              │ │
                                      │ │ What's Wrong            │ │
                                      │ └─────────────────────────┘ │
                                      └──────────────┬──────────────┘
                                                     │
                                          ┌──────────┴──────────┐
                                          ▼                     ▼
                                    Nothing stale         Sections stale
                                    ──▶ tsu push          ──▶ tsu generate
                                                          ──▶ tsu push
```

```bash
# after making code changes
tsu diff                  # diff against HEAD (uncommitted changes)
tsu diff HEAD~3           # or check last 3 commits
# review .tsu/diff.md — decide whether to regenerate
tsu generate              # only if needed
tsu push
```

---

## 16. PR Gate — Doc Staleness Check in CI

Run `tsu diff` in CI on every pull request to detect whether the PR
introduces code changes that make documentation stale. Flag it as a check
failure or leave a PR comment — catch doc rot *before* merge.

```
┌──────────────────────────────────────────────────────────────────┐
│                       CI/CD Pipeline (PR)                         │
│                                                                   │
│  ┌────────────────┐     ┌────────────────────┐                   │
│  │  Checkout PR   │────▶│ tsu diff main..HEAD │──┐               │
│  └────────────────┘     └────────────────────┘  │               │
│                                                  │               │
│                              ┌───────────────────┤               │
│                              ▼                   ▼               │
│                        All clear           Stale sections        │
│                        ──▶ ✅ Pass         ──▶ ❌ Fail / Comment │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### GitHub Actions example

```yaml
- name: Check doc impact
  run: |
    pip install tsu-cli
    tsu diff main..HEAD --profile tech
    # Parse diff.md for "No stale content" / "No new undocumented content"
    if grep -q "is now stale\|not yet documented" .tsu/diff.md; then
      echo "::warning::This PR introduces documentation gaps. Run 'tsu generate' to update."
    fi
```

---

## 17. Post-Release Doc Audit

After tagging a release, generate a diff report showing what changed between
the previous release and the current one. Hand this to product, ops, or
support teams as a "here's what the docs are missing" summary.

```
┌────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│ git tag    │────▶│ tsu diff v1.2.0..    │────▶│ .tsu/diff.md     │
│  v1.3.0   │     │          v1.3.0      │     │                  │
└────────────┘     └──────────────────────┘     │ "These sections  │
                                                │  need updating   │
                                                │  for v1.3.0"     │
                                                └──────────────────┘
```

```bash
git tag v1.3.0
tsu diff v1.2.0..v1.3.0
# .tsu/diff.md now summarises what changed between releases
# Share with product/ops or use it to guide a targeted tsu generate
```

---

## 18. Confluence Drift Detection with `tsu diff --remote`

Detect when someone manually edited the Confluence page — added a note,
fixed a typo, restructured sections. Before the next `tsu generate`
overwrites those edits, see exactly what was changed on the page.

```
┌────────────┐                               ┌─────────────┐
│  Someone   │──── edits page manually ─────▶│  Confluence  │
│  (PM, QA)  │                               └──────┬──────┘
└────────────┘                                       │
                                                     │
┌────────────────────────────────────────────────────┘
│
▼
┌──────────────────┐     ┌──────────────────────────────────┐
│ tsu diff --remote│────▶│ .tsu/diff.md                     │
└──────────────────┘     │ What's Stale: (remote has edits) │
                         │ What's New: (remote additions)   │
                         │ What's Wrong: (inconsistencies)  │
                         └──────────────────────────────────┘
```

```bash
tsu diff --remote             # compare local doc vs live Confluence page
# review .tsu/diff.md
# decide: pull remote changes? regenerate? push local version?
```

This is especially useful before running `tsu generate`, which pulls the
remote page and feeds it to the LLM. Knowing what changed remotely helps
you decide whether to preserve or override those edits.

---

## 19. Scheduled Doc Health Check (CI Cron)

Run `tsu diff` on a weekly schedule in CI to produce a "doc freshness"
report. Post it to Slack, email, or a dashboard — teams get a regular
pulse on documentation health without anyone manually auditing.

```
┌──────────────────────────────────────────────────────────────────┐
│                  Scheduled CI Job (weekly)                         │
│                                                                   │
│  ┌────────────────┐     ┌───────────────────┐     ┌────────────┐ │
│  │  Checkout repo │────▶│ tsu diff HEAD~50  │────▶│ Post to    │ │
│  └────────────────┘     └───────────────────┘     │ Slack /    │ │
│                                                    │ Dashboard  │ │
│                                                    └────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### GitHub Actions example

```yaml
on:
  schedule:
    - cron: "0 9 * * 1"  # every Monday at 9am

jobs:
  doc-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 50
      - run: |
          pip install tsu-cli
          tsu diff HEAD~50 --profile tech
      - name: Post to Slack
        if: always()
        run: |
          REPORT=$(cat .tsu/diff.md)
          curl -X POST "$SLACK_WEBHOOK" \
            -H 'Content-type: application/json' \
            -d "{\"text\": \"Weekly Doc Health Report:\n$REPORT\"}"
```

---

## 20. Multi-Profile Drift Detection

Audit each documentation profile independently. The API spec might be
current while the security doc is stale — `tsu diff` shows that per-profile
instead of one monolithic check.

```
┌───────────┐     ┌──────────────────────────┐     ┌────────────────────────┐
│  Codebase │────▶│ tsu diff --profile tech  │────▶│ tech:     ✅ current   │
│  changes  │     │ tsu diff --profile api   │     │ api:      ❌ stale     │
│           │     │ tsu diff --profile sec   │     │ security: ❌ stale     │
└───────────┘     └──────────────────────────┘     └────────────────────────┘
```

```bash
tsu diff --profile tech       # .tsu/diff.md
tsu diff --profile api        # .tsu/diff-api.md
tsu diff --profile security   # .tsu/diff-security.md
# each report tells you independently which profile needs regeneration
```

---

## 21. Onboarding — Trust Audit for New Team Members

New team member runs `tsu diff` against a broad range of commits on a
project they're joining. The report instantly shows which parts of the
docs are trustworthy vs. which have drifted — faster ramp-up with less
"is this doc still accurate?" uncertainty.

```bash
# joining a new project
git clone <repo>
cd <repo>
tsu diff HEAD~100             # audit docs against last 100 commits
# .tsu/diff.md tells you what's reliable and what's stale
```
