# tsu-cli

Generate project documentation using GitHub Copilot SDK and integrate with document storage tools like Confluence.

## ⚠️ AI Usage Disclosure
This project was developed with the assistance of Artificial Intelligence (AI) tools, including [e.g., Claude/Copilot]. While I have reviewed, verified and tested the code, portions of the codebase were generated automatically.

*   **Human Review:** The code has been reviewed by me for accuracy, but potential bugs or edge cases may exist.
*   **Best Practice:** Users are encouraged to carefully inspect code before using it in production environments.

## Prerequisites

- **Python 3.11+**
- **GitHub Copilot CLI** — installed and authenticated ([installation guide](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli))
- **Confluence API token** — for pushing pages ([create one here](https://id.atlassian.com/manage-profile/security/api-tokens))

## Installation

```bash
pip install tsu-cli
```

### Development install

```bash
git clone https://github.com/vivekrana2012/tsu-cli.git
cd tsu-cli
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Initialize in your project directory
cd /path/to/your/project
tsu init

# 2. Generate tech documentation
tsu generate

# 3. Push to Confluence
tsu push
```

### What happens during setup

1. **`tsu init`** creates a `.tsu/` directory with configuration and a prompt file.
2. If you provide a Confluence parent page URL and credentials, a blank placeholder
   page is created immediately — locking the `page_id` so future pushes (including
   CI/CD) update the same page instead of creating duplicates.
3. **`tsu generate`** sends your codebase to a Copilot-powered LLM and writes
   `.tsu/document.md`. If a Confluence page already exists, its content is pulled
   first so manual edits are preserved.
4. **`tsu push`** converts the markdown to Confluence storage format and uploads it.

## Commands

### `tsu init`

Interactive setup — creates `.tsu/` directory with configuration files.

If you provide a parent page URL and credentials, a blank placeholder page is
created on Confluence during init. The `page_id` is saved in
`.tsu/confluence.json` so that all future `tsu push` runs (including from
CI/CD pipelines like Jenkins) update the same page instead of creating
duplicates. Re-running `tsu init` preserves the existing `page_id`.

```bash
tsu init
tsu init --dir /path/to/project
tsu init --profile func        # initialize a custom profile
```

| Flag | Description | Default |
| ---- | ----------- | ------- |
| `-d, --dir` | Project directory | current directory |
| `-p, --profile` | Profile name | `tech` |

### `tsu generate`

Analyze the project using GitHub Copilot and generate `.tsu/document.md`.

If a Confluence page already exists, the current page content is pulled and
sent to the LLM as reference — preserving any manually added content while
updating sections based on the latest codebase.

```bash
tsu generate
tsu generate --model claude-sonnet-4.5
tsu generate --output custom-doc.md
tsu generate --extra "Focus on the authentication flow"
tsu generate --offline           # skip Confluence sync, generate fresh
tsu generate --profile func      # generate for a specific profile
```

| Flag | Description | Default |
| ---- | ----------- | ------- |
| `-d, --dir` | Project directory | current directory |
| `-m, --model` | LLM model name (`auto` uses SDK default) | value in `config.json` |
| `-o, --output` | Output file path | `.tsu/document.md` |
| `-e, --extra` | One-off instructions appended to the prompt | — |
| `-p, --profile` | Profile name | `tech` |
| `--offline` | Skip Confluence sync, generate fresh from codebase only | off |

### `tsu push`

Upload `.tsu/document.md` to Confluence. Creates a new page on first push,
updates the existing page on subsequent pushes (version is incremented
automatically).

```bash
tsu push
tsu push --profile func
```

| Flag | Description | Default |
| ---- | ----------- | ------- |
| `-d, --dir` | Project directory | current directory |
| `-p, --profile` | Profile name | `tech` |

### `tsu pull`

Fetch the remote Confluence page as markdown and save it locally. Requires a
`page_id` in the profile's Confluence config.

```bash
tsu pull
tsu pull --profile func
```

| Flag | Description | Default |
| ---- | ----------- | ------- |
| `-d, --dir` | Project directory | current directory |
| `-p, --profile` | Profile name | `tech` |

### `tsu profiles`

Show all initialized profiles and available built-in profiles.

```bash
tsu profiles
tsu profiles --dir /path/to/project
```

### `tsu models`

List available LLM models from the Copilot SDK.

```bash
tsu models
```

### `tsu help`

Show a detailed guide covering the full workflow, all commands, flags,
authentication, prompt customization, and examples.

```bash
tsu help
```

### `tsu auth`

Manage Confluence credentials (stored in system keychain, never on disk).

```bash
tsu auth set      # Store email + token in keychain
tsu auth status   # Check credential configuration
tsu auth clear    # Remove stored credentials
```

### `tsu --version`

Print the installed version.

```bash
tsu --version
tsu -v
```

## Profiles

Profiles let you maintain **multiple independent documents** from the same
project — for example a *tech overview*, a *functional spec*, and an *API
reference* — each with its own prompt file, Confluence page, and output
file.

The default profile is **`tech`**. Create additional profiles by passing
`--profile <name>` to `init`, `generate`, `push`, or `pull`.

### Built-in profiles

Three pre-defined profiles ship with tsu-cli. When you init a profile whose
name matches a built-in profile, the tailored prompt is seeded automatically
instead of the generic tech profile:

| Profile name | Focus |
| ------------ | ----- |
| `api_spec` | API endpoints, request/response schemas, auth, error codes |
| `func_spec` | Business rules, workflows, validation logic, data transformations |
| `security_spec` | Auth mechanisms, data handling, input validation, threat surface |

Run `tsu profiles` to see which profiles are available and which are already
initialized.

### Creating and using profiles

```bash
# Initialize profiles (built-in profiles are seeded automatically)
tsu init                            # default "tech" profile
tsu init --profile api_spec         # API specification
tsu init --profile func_spec        # functional specification
tsu init --profile security_spec    # security overview
tsu init --profile custom-name      # custom profile (uses generic prompt)

# Generate & push per profile
tsu generate --profile api_spec
tsu push --profile func_spec

# See all profiles + available profiles
tsu profiles
```

### Per-profile files

Each profile gets its own set of files inside `.tsu/`:

| File type | `tech` (default) | Custom profile `{name}` |
| --------- | ----------------- | ----------------------- |
| Confluence config | `confluence.json` | `confluence-{name}.json` |
| Prompt file | `generate.md` | `generate-{name}.md` |
| Generated output | `document.md` | `document-{name}.md` |

`config.json` (model selection) is shared across all profiles.

Re-running `tsu init` for an existing profile preserves the `page_id` and
will not overwrite an edited prompt file.

## Configuration

All config lives in `.tsu/` (safe to commit — no secrets):

| File | Purpose |
| ---- | ------- |
| `config.json` | Shared tool settings (LLM model) |
| `confluence.json` | Confluence page target (per profile) |
| `generate.md` | Prompt file (per profile, editable) |
| `document.md` | Generated documentation (per profile) |

### Confluence Credentials

Credentials are resolved in this order (never stored in config files):

1. Environment variables: `CONFLUENCE_USER`, `CONFLUENCE_TOKEN`
2. System keychain (via `tsu auth set`)
3. Interactive prompt

Use environment variables for CI/CD pipelines.

## Customizing the Prompt

`tsu init` copies the default prompt file to `.tsu/generate.md` (or
`.tsu/generate-{profile}.md` for custom profiles). Edit it freely — your
changes are used on every subsequent `tsu generate` run, and re-running
`tsu init` will **not** overwrite an existing prompt file.

### Default sections

The default profile ships with six sections. You can add, remove, reorder, or
rewrite any of them:

| # | Section | Format |
| - | ------- | ------ |
| 1 | **Overview** | 2-4 paragraphs — what the project does, language, framework |
| 2 | **Tech Stack & Frameworks** | Table: Category · Technology · Version · Notes |
| 3 | **Architecture** | Prose + ASCII/Unicode architecture diagram + flow diagram + component responsibilities table |
| 4 | **API Endpoints** | Table: Method · Path · Description (skipped if none found) |
| 5 | **Configuration** | Table per config source: Key · Type · Default · Required · Description |
| 6 | **Dependencies Summary** | Table: Dependency · Version · Purpose |

### How to customize

- **Add a section** — append a new `## 7. Security` heading with instructions.
- **Remove a section** — delete the heading and its instructions from the file.
- **Change detail level** — rewrite the instructions under a heading (e.g.
  "Write a single paragraph" instead of "Use a table").
- **One-off tweaks** — use `--extra` without editing the prompt file:
  ```bash
  tsu generate --extra "Focus on the authentication flow"
  tsu generate --extra "Write in Japanese"
  tsu generate --extra "Skip the dependencies section"
  ```

## License

MIT
