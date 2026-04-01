# tsu-cli

Generate project tech documentation using GitHub Copilot SDK and push to Confluence.

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
```

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
tsu generate --offline    # skip Confluence sync, generate fresh
```

### `tsu models`

List available LLM models from the Copilot SDK.

```bash
tsu models
```

### `tsu push`

Upload `.tsu/document.md` to Confluence. Creates a new page on first push,
updates the existing page on subsequent pushes.

```bash
tsu push
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

## Configuration

All config lives in `.tsu/` (safe to commit — no secrets):

| File               | Purpose                              |
| ------------------ | ------------------------------------ |
| `config.json`      | Tool settings (model, output file)   |
| `confluence.json`  | Confluence page target               |
| `generate.md`      | Prompt template (editable)           |
| `document.md`      | Generated documentation              |

### Confluence Credentials

Credentials are resolved in this order (never stored in config files):

1. Environment variables: `CONFLUENCE_USER`, `CONFLUENCE_TOKEN`
2. System keychain (via `tsu auth set`)
3. Interactive prompt

Use environment variables for CI/CD pipelines.

## Customizing the Prompt

`tsu init` copies the default prompt template to `.tsu/generate.md`. Edit it
freely to change the document structure, sections, or instructions — your
changes are used on every subsequent `tsu generate` run.

The template uses Jinja2 syntax. The variable `{{ additional_instructions }}`
is populated by the `--extra` flag.

Re-running `tsu init` will **not** overwrite an existing `.tsu/generate.md`,
so your edits are safe.

## License

MIT
