```
 _____              ___ _     ___
|_   _|___  _   _  / __| |   |_ _|
  | | / __|| | | || |  | |    | |
  | | \__ \| |_| || |__| |___ | |
  |_| |___/ \__,_| \___|_____|___|
```

# tsu-cli — Project Documentation Generator

Analyze your code with GitHub Copilot and produce comprehensive
markdown documents which can be pushed to remote document stores like Confluence.

Supports multiple **document profiles** — generate different document types
(tech overview, functional rules, business rules, etc.) from the same codebase.

Three-step workflow: **init → generate → push**

---

## Step 1: Initialize

```
tsu init
```

Run this once per project (and once per profile). It creates a `.tsu/` directory containing:

| File               | Purpose                              |
| ------------------ | ------------------------------------ |
| `config.json`      | Tool settings (LLM model)            |
| `confluence.json`  | Confluence page target (per profile) |
| `generate.md`      | Prompt file (editable, per profile) |

The whole `.tsu/` directory is safe to commit — no secrets are stored on disk.

**Profiles:**

Use `--profile` to initialize additional document types:

```bash
tsu init                          # default 'tech' profile
tsu init --profile api_spec       # add an API specification profile
tsu init --profile func_spec      # add a functional specification profile
tsu init --profile security_spec  # add a security overview profile
tsu init --profile custom-name    # add a custom profile
```

**Built-in profiles:**

Three pre-defined profiles ship with tsu-cli. When a profile name matches a
built-in profile, the tailored prompt is seeded automatically instead of the
generic tech prompt:

| Profile name    | Focus                                                     |
| --------------- | --------------------------------------------------------- |
| `api_spec`      | API endpoints, request/response schemas, auth, error codes|
| `func_spec`     | Business rules, workflows, validation logic, data transforms |
| `security_spec` | Auth mechanisms, data handling, input validation, threat surface |

For any other profile name, the generic tech prompt is seeded and you
customize it manually.

Run `tsu profiles` to see available profiles and initialized profiles.

Each profile gets its own prompt file, Confluence page target, and output
file. The default `tech` profile uses `generate.md`, `confluence.json`, and
`document.md`. Custom profiles use `generate-{name}.md`, `confluence-{name}.json`,
and `document-{name}.md`.

Adding a profile to an existing project only creates the new profile's files —
it does not touch `config.json` or other profiles.

The whole `.tsu/` directory is safe to commit — no secrets are stored on disk.

**Blank page creation:**

If you provide a parent page URL and credentials during init, tsu automatically
creates a blank placeholder page on Confluence and saves the `page_id` in
`.tsu/confluence.json`. This ensures that all subsequent `tsu push` runs —
including from CI/CD pipelines like Jenkins — update the **same page** instead
of creating duplicates. (CI environments typically cannot write the `page_id`
back to config, so pre-creating the page during init solves this.)

If credentials are not available or the API call fails, init continues
normally — the page will be created on the first `tsu push` instead.

Re-running `tsu init` on a project that already has a `page_id` will preserve
it, so you won't end up with orphaned duplicate pages.

**Options:**

| Flag              | Description                                       |
| ----------------- | ------------------------------------------------- |
| `-d`, `--dir`     | Project directory (defaults to current directory) |
| `-p`, `--profile` | Profile to initialize (defaults to `tech`)        |

**Examples:**

```bash
cd ~/projects/my-app
tsu init

# Initialize a different project
tsu init --dir /path/to/other/project

# Add a functional specification profile
tsu init --profile func_spec
```

---

## Step 2: Customize the Prompt (Optional)

Edit `.tsu/generate.md` (or `.tsu/generate-{profile}.md` for custom profiles)
to control what the generated document contains.
This file is a Jinja2 template that instructs the Copilot agent on how to
analyze your project and what sections to produce.

For the `tech` profile, the seeded prompt works as-is. For custom profiles,
you **must** edit the seeded prompt to replace the tech-specific sections
with your own document structure (e.g. business rules, validation logic, etc.).

**Default sections produced:**

1. **Overview** — what the project does, purpose, key characteristics
2. **Tech Stack & Frameworks** — language, framework, database, build tools (table)
3. **Architecture** — high-level design with ASCII diagrams:
   - Architecture diagram (component relationships)
   - Flow diagram (request/data flow)
   - Component responsibilities table
4. **API Endpoints** — REST/GraphQL endpoints table (if applicable)
5. **Configuration** — env vars, config files, CLI options (tables per source)
6. **Dependencies Summary** — key dependencies with purpose (table)

**How to customize:**

- **Add sections** — e.g., add a "Security" or "Deployment" section with specific instructions
- **Remove sections** — delete any section heading and its instructions
- **Rewrite instructions** — change diagram style, level of detail, language, etc.
- **Change the output format** — request different table structures, bullet lists, etc.

**Jinja2 variable:**

The placeholder `{{ additional_instructions }}` in the prompt file is replaced at
generation time by whatever you pass via `--extra`. You don't need to modify
the prompt to use `--extra` — it just appends to the end.

**Important:** Re-running `tsu init` will **not** overwrite an existing
`.tsu/generate.md`, so your edits are always safe.

---

## Step 3: Generate Documentation

```
tsu generate
```

The Copilot agent autonomously explores your project directory — reading
source files, config files, and package manifests — then produces a
comprehensive markdown document at `.tsu/document.md`.

**Confluence sync (default):**

If a Confluence page already exists (`page_id` is set in `confluence.json`
and credentials are available), the current page content is automatically
pulled and sent to the LLM as reference context. This means:

- Manually added sections on the Confluence page are preserved
- Outdated sections are updated based on the current codebase
- Information that is no longer accurate is removed

If no `page_id` exists (first run), no credentials are configured, or the
API call fails, generation proceeds fresh — no error, no extra setup needed.

Use `--offline` to explicitly skip the sync and generate from codebase only.

**Options:**

| Flag             | Description                                         |
| ---------------- | --------------------------------------------------- |
| `-m`, `--model`  | LLM model (e.g. `gpt-4o`, `claude-sonnet-4.5`)      |
| `-o`, `--output` | Output file path override                           |
| `-e`, `--extra`  | Additional instructions appended to the prompt      |
| `-d`, `--dir`    | Project directory (defaults to current directory)   |
| `-p`, `--profile`| Document profile to generate (defaults to `tech`)   |
| `--offline`      | Skip Confluence sync, generate from codebase only   |

**Examples:**

```bash
# Generate with defaults (syncs with Confluence if page exists)
tsu generate

# Generate without pulling existing page
tsu generate --offline

# Use a different model
tsu generate --model claude-sonnet-4.5

# Save to a custom path
tsu generate --output docs/tech-overview.md

# Add one-off instructions without editing the prompt
tsu generate --extra "Focus on the authentication flow"

# Write documentation in a different language
tsu generate --extra "Write in Japanese"

# Combine flags
tsu generate -m gpt-4o -e "Skip the dependencies section"

# Generate for a specific profile
tsu generate --profile func_spec
tsu generate --profile api_spec --model claude-sonnet-4.5
```

**Model validation:**

`tsu generate` validates the model name against the Copilot SDK's available
models before starting. If the model is not recognized, it prints the list
of available models and exits. Use `tsu models` to see the list at any time.

---

## Step 4: Push to Confluence (Optional)

```
tsu push
```

Uploads `.tsu/document.md` to Confluence as a page.

**Options:**

| Flag              | Description                                       |
| ----------------- | ------------------------------------------------- |
| `-d`, `--dir`     | Project directory (defaults to current directory) |
| `-p`, `--profile` | Profile to push (defaults to `tech`)              |

**Examples:**

```bash
tsu push
tsu push --dir /path/to/project
tsu push --profile func_spec
```

---

## Authentication

### Confluence Credentials

Credentials are resolved in this order (first match wins):

1. **Environment variables:** `CONFLUENCE_USER` and `CONFLUENCE_TOKEN`
2. **System keychain** (via `tsu auth set`)
3. **Interactive prompt** (offered during `tsu init`)

Use environment variables for CI/CD pipelines. Use the keychain for local
development.

**Auth commands:**

| Command            | Description                                |
| ------------------ | ------------------------------------------ |
| `tsu auth set`     | Store email + API token in system keychain |
| `tsu auth status`  | Show where credentials are configured      |
| `tsu auth clear`   | Remove stored credentials from keychain    |

**Examples:**

```bash
# Store credentials interactively
tsu auth set

# Check what's configured
tsu auth status

# Use environment variables (e.g. in CI)
export CONFLUENCE_USER="you@company.com"
export CONFLUENCE_TOKEN="your-api-token"
tsu push
```

### GitHub Copilot Auth

Copilot authentication is handled by the Copilot SDK. Make sure you are
logged in via the `copilot` CLI, or set one of these environment variables:

- `GITHUB_TOKEN`
- `COPILOT_GITHUB_TOKEN`

---

## Typical Workflow

```bash
cd ~/projects/my-app
tsu init                                          # one-time setup (tech profile)
vim .tsu/generate.md                              # optional: customize prompt
tsu generate                                      # analyze project → .tsu/document.md
cat .tsu/document.md                              # review the output
tsu generate --extra "Add more detail to the API section"   # re-generate with tweaks
tsu push                                          # upload to Confluence

# Add a functional specification profile
tsu init --profile func_spec
vim .tsu/generate-func_spec.md                       # customize for functional rules
tsu generate --profile func_spec                     # generate → .tsu/document-func_spec.md
tsu push --profile func_spec                         # push to separate Confluence page
```

After the initial setup, the day-to-day loop is just:

**`tsu generate [--profile X]` → review → `tsu push [--profile X]`**

---

## Files Reference

| File                          | Purpose                                     |
| ----------------------------- | ------------------------------------------- |
| `.tsu/config.json`            | LLM model settings (shared across profiles) |
| `.tsu/confluence.json`        | Confluence target for `tech` profile        |
| `.tsu/confluence-{name}.json` | Confluence target for custom profile        |
| `.tsu/generate.md`            | Prompt file for `tech` profile              |
| `.tsu/generate-{name}.md`    | Prompt file for custom profile              |
| `.tsu/document.md`            | Generated output for `tech` profile         |
| `.tsu/document-{name}.md`    | Generated output for custom profile         |
