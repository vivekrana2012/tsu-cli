# Plan: tsu-cli — Project Doc Generator

A Python CLI (`tsu`) using Typer + GitHub Copilot SDK that analyzes the current project and produces Confluence-ready documentation with Mermaid flow diagrams (greyscale themed). Supports multiple **document profiles** (e.g. tech overview, functional rules, business rules) — each profile has its own prompt template, output file, and Confluence page target. Three-step workflow: `tsu init` → `tsu generate` → `tsu push`. Prompts stored as external Jinja2 templates for easy editing. Confluence upload via direct REST calls with `httpx`. Token managed via keyring/env var. The `.tsu/` directory is fully git-trackable — no secrets stored on disk.

## Project Structure

```
tsu-cli/
├── pyproject.toml
├── README.md
├── .gitignore
└── src/
    ├── __init__.py
    ├── main.py              # Typer app: init, generate, push, auth
    ├── generator.py         # Copilot SDK integration
    ├── publisher.py         # Confluence REST calls via httpx
    ├── config.py            # Config read/write + prompt seeding
    ├── auth.py              # Token management (keyring + env var)
    ├── help.md              # Detailed usage guide (rendered by tsu help)
    └── prompts/
        ├── __init__.py      # Package marker (importlib.resources)
        └── generate.md      # Default prompt template (seed source for all profiles)
```

### Dependencies

- `github-copilot-sdk` — Copilot agent runtime
- `typer[all]` — CLI framework
- `httpx` — HTTP client for Confluence REST API
- `rich` — Terminal output formatting
- `keyring` — System keychain for secrets
- `markdown` — Markdown to HTML conversion
- `jinja2` — Prompt template rendering

Entry point: `tsu = "src.main:app"`

## `.tsu/` Directory (Git-Tracked)

All files in `.tsu/` are non-sensitive and safe to commit. The whole team shares the same config and page targets.

### `.tsu/config.json`

```json
{
  "model": "gpt-4o"
}
```

### Profile-Specific Files

Each profile has its own prompt template, Confluence config, and output file. The **`tech` profile** (default) uses legacy filenames for backward compatibility with existing `.tsu/` directories. Custom profiles use a `-{profile}` suffix.

| File | `tech` profile (default) | Custom profile (e.g. `func`) |
|------|--------------------------|------------------------------|
| Prompt template | `.tsu/generate.md` | `.tsu/generate-func.md` |
| Confluence config | `.tsu/confluence.json` | `.tsu/confluence-func.json` |
| Generated output | `.tsu/document.md` | `.tsu/document-func.md` |

### `.tsu/confluence.json` (per-profile)

```json
{
  "confluence_url": "https://yourcompany.atlassian.net/wiki",
  "space_key": "ENG",
  "page_title": "MyProject - Tech Overview",
  "page_id": null,
  "parent_page_id": "12345",
  "mermaid_macro": "mermaid-cloud"
}
```

For a custom profile like `func`, this would be `.tsu/confluence-func.json` with its own `page_title`, `page_id`, etc.

### `.tsu/generate.md` (per-profile)

Prompt template (Jinja2). Seeded from the built-in default during `tsu init --profile <name>`.
The user edits this file to customize the document structure and generation
instructions. Re-running `tsu init` for the same profile will **not** overwrite an existing copy.

All profiles are seeded from `src/prompts/generate.md`. For the `tech` profile this works as-is. For custom profiles, the user edits the seeded copy to replace the tech-specific sections with their own document structure.

### `.tsu/document.md` (per-profile)

Generated output. Reviewable in PRs before pushing to Confluence.

### Discovering Profiles

`config.py` provides `list_profiles(project_dir)` — scans `.tsu/` for `generate*.md` files and returns profile names. Useful for tooling and validation.

## Commands

### 1. `tsu init` — Interactive Setup

- **`--profile` flag** (default: `tech`) — selects which profile to initialize.
- Creates `.tsu/` directory with `config.json` (if not already present).
- Creates profile-specific files: prompt template and Confluence config.
- Prompts interactively via `typer.prompt()` for each field.
- Page title defaults to directory name (with profile suffix for non-tech profiles).
- Confluence fields are optional (skip for markdown-only workflow).
- At the end, prompts for Confluence credentials and stores them in the system keychain (shared across profiles).
- **Blank page creation:** If a parent page URL and credentials are available, creates a blank placeholder page on Confluence and saves the `page_id` to the profile's `confluence.json`. This prevents CI/CD pipelines (e.g. Jenkins) from creating duplicate pages on every push, since they cannot write the `page_id` back to config. If credentials are unavailable or the API call fails, init continues normally — the page will be created on first `tsu push` instead.
- **Re-init guard:** If a profile already exists with a `page_id`, the existing `page_id` is preserved to avoid creating orphaned duplicate pages.
- **Adding profiles to existing projects:** If `.tsu/` already exists (from a previous `tsu init`), running `tsu init --profile func` only creates the new profile's files (`generate-func.md`, `confluence-func.json`) without touching existing config or other profiles.

**Example: Adding a functional rules profile to an existing project**

```bash
tsu init --profile func
# Seeds .tsu/generate-func.md (base template — user customizes this)
# Creates .tsu/confluence-func.json (separate page target)
# Optionally creates a blank Confluence page for the func profile
```

### 2. `tsu generate` — Analyze Project + Produce Markdown

- **`--profile` flag** (default: `tech`) — selects which profile's prompt and output to use.
- **Profile validation:** Checks that the profile's prompt template exists (e.g. `.tsu/generate-func.md`). If missing, prints an error directing the user to run `tsu init --profile <name>`.
- **Confluence sync (default):** Before generation, pulls the existing Confluence page HTML if `page_id` exists in the profile's `confluence.json` and credentials are available. The HTML is passed to the LLM as reference context via the `{{ existing_document }}` template variable, so manually added content is preserved and outdated sections are updated. If `page_id` is missing, credentials are unavailable, or the API call fails, generation proceeds fresh without error.
- `--offline` flag skips the sync entirely and generates from codebase only.
- Reads the prompt template from the profile's prompt file (e.g. `.tsu/generate.md` for `tech`, `.tsu/generate-func.md` for `func`)
  - Renders Jinja2 variables: `additional_instructions` (from `--extra`), `existing_document` (from Confluence sync)
- Creates `CopilotClient(cwd=os.getcwd())`, opens a session
- Sends the rendered prompt — the Copilot agent autonomously uses its built-in tools (`read_file`, `list_dir`, `grep`, etc.) to explore the project
- Collects the final `assistant.message` content
- Writes to the profile's output file (e.g. `.tsu/document.md` for `tech`, `.tsu/document-func.md` for `func`)
- Flags: `--output`, `--model`, `--extra`, `--offline`, `--profile`
- **Model validation:** Before generation, queries the Copilot SDK via `list_models()` and rejects unknown model names with a list of valid options. During `tsu init`, available models are shown as a hint and invalid names trigger a warning with confirmation.
- Shows a rich summary on completion (profile name, file path, section count, word count)

### 3. `tsu push` — Upload to Confluence via REST API

All calls use `httpx` with HTTP Basic auth (user email + API token).

| Action        | Method | Endpoint                                     |
| ------------- | ------ | -------------------------------------------- |
| Get page      | GET    | `/rest/api/content/{page_id}?expand=version` |
| Create page   | POST   | `/rest/api/content`                          |
| Update page   | PUT    | `/rest/api/content/{page_id}`                |

**Create flow** (when `page_id` is null):

```json
{
  "type": "page",
  "title": "{page_title}",
  "space": {"key": "{space_key}"},
  "ancestors": [{"id": "{parent_page_id}"}],
  "body": {"storage": {"value": "<html>...", "representation": "storage"}}
}
```

**Update flow** (when `page_id` exists):

- GET the page to read current `version.number`
- PUT with incremented version number

**Edge cases:**

- 404 on existing `page_id` → page was deleted → re-create and update config
- Markdown → HTML via `markdown` library
- Mermaid blocks wrapped in `<ac:structured-macro ac:name="{mermaid_macro}">` for Confluence rendering

**After successful create:** writes `page_id` back to the profile's `confluence.json` (e.g. `.tsu/confluence.json` for `tech`, `.tsu/confluence-func.json` for `func`) so subsequent pushes are updates.

- **`--profile` flag** (default: `tech`) — selects which profile's document and Confluence page to push.
- Reads the document from the profile's output file (e.g. `.tsu/document-func.md` for `func`).
- Uses the profile's Confluence config for the target page.

### 4. `tsu auth` — Manage Confluence Credentials

Token resolution priority:

1. `CONFLUENCE_TOKEN` env var (for CI/scripts)
2. System keychain via `keyring` (service=`tsu-cli`, username=`confluence`)
3. Interactive prompt (offers to store in keychain)

User email resolution:

1. `CONFLUENCE_USER` env var
2. System keychain (service=`tsu-cli`, username=`confluence-user`)
3. Interactive prompt

Subcommands:

- `tsu auth set` — prompt for email + token, store in keychain
- `tsu auth clear` — remove credentials from keychain
- `tsu auth status` — show whether credentials are configured (env/keyring/none) without revealing values

### 5. `tsu help` — Detailed Usage Guide

Prints a comprehensive, Rich-formatted guide covering the full workflow:

- **Step 1: Initialize** — what `tsu init` creates, `--profile` flag, examples for tech and custom profiles
- **Step 2: Customize the Prompt** — default sections in `.tsu/generate.md`, how to add/remove/rewrite sections, Jinja2 `{{ additional_instructions }}` variable, customization examples, creating custom profiles
- **Step 3: Generate Documentation** — all flags (`--model`, `--output`, `--extra`, `--dir`, `--profile`), examples including model override, custom output path, extra instructions, multi-language, profile selection
- **Step 4: Push to Confluence** — create/update behavior, page ID persistence, `--profile` flag, per-profile pages
- **Profiles** — how profiles work, file naming conventions, creating and managing profiles
- **Authentication** — Confluence credential resolution order (env → keychain → prompt), `tsu auth` subcommands, GitHub Copilot auth via SDK/env vars
- **Typical Workflow** — end-to-end example from `tsu init` through `tsu push`, including multi-profile workflow
- **Files Reference** — table of all `.tsu/` files and their purpose, profile-specific file naming

The content lives in `src/help.md` (plain markdown), loaded via `importlib.resources` and rendered with `rich.markdown.Markdown`. The command is registered as `hidden=True` so it doesn't clutter `tsu --help`.

## Prompt Templates

### Built-in: `src/prompts/generate.md`

The single built-in prompt template, used as the seed for **all** profiles. Instructs the Copilot agent to:

- Explore the project directory structure
- Read key config files
- Identify tech stack, architecture, API endpoints, dependencies
- Produce markdown with sections: Overview, Tech Stack, Architecture, API Endpoints, Dependencies
- Include Mermaid flowcharts with a greyscale theme

Mermaid greyscale theme (embedded in prompt):

```
%%{init: {'theme': 'base', 'themeVariables': {
  'primaryColor': '#e0e0e0',
  'primaryTextColor': '#1a1a1a',
  'primaryBorderColor': '#888888',
  'lineColor': '#666666',
  'secondaryColor': '#f5f5f5',
  'tertiaryColor': '#cccccc',
  'nodeTextColor': '#1a1a1a'
}}}%%
```

Seeded into the profile's prompt file during `tsu init --profile <name>` (e.g. `.tsu/generate.md` for `tech`, `.tsu/generate-func.md` for `func`). For the `tech` profile, the prompt works as-is. For custom profiles, the user edits the seeded copy to replace the tech-specific sections with their document type's structure (e.g. business rules, functional specs, etc.). Never overwritten by subsequent init runs.

### Custom Profile Workflow

```bash
# 1. Initialize a new profile
tsu init --profile func

# 2. Edit the seeded prompt template to define your document structure
#    e.g. add sections for Business Rules, Validation Logic, Data Flow, etc.
vim .tsu/generate-func.md

# 3. Generate the document
tsu generate --profile func

# 4. Push to Confluence (goes to the func profile's page)
tsu push --profile func
```

Adding new document types requires **no code changes** — just a new profile with a customized prompt.

## Authentication & Security

- **Secure by default:** No secrets on disk. Token and user email live in keychain or env vars only.
- `.tsu/` is safe to commit as-is — contains only configuration and generated artifacts.
- Copilot SDK auth: relies on `copilot` CLI being logged in (`use_logged_in_user=True`), or `GITHUB_TOKEN` / `COPILOT_GITHUB_TOKEN` env var.

## Verification

### Manual Verification

#### Existing (tech profile — backward compat)

- `pip install -e .` then `tsu --help` — all subcommands visible
- `tsu init` in a sample project — creates `.tsu/config.json` and `.tsu/confluence.json`
- `tsu generate` — produces `.tsu/document.md` with Mermaid blocks using greyscale theme
- `tsu generate` with existing `page_id` + credentials → syncs with Confluence, preserves manual content
- `tsu generate --offline` → skips sync, generates fresh
- `tsu generate` without `page_id` → generates fresh, no error
- Edit `.tsu/generate.md` → verify `tsu generate` picks up the changes
- `tsu help` — prints the full workflow guide with formatted output
- `tsu auth set` + `tsu auth status` — credentials stored and confirmed
- `tsu models` — lists available models from the Copilot SDK
- `tsu generate` with invalid model name → error with available models listed
- `tsu push` — creates/updates Confluence page, `page_id` written back to config
- Render `document.md` in a Mermaid previewer → confirm greyscale styling

#### Profile system

- `tsu init --profile func` — creates `.tsu/generate-func.md` (seeded from `generate.md`) and `.tsu/confluence-func.json`; does NOT overwrite existing `config.json` or tech profile files
- `tsu init --profile func` when profile already exists — preserves existing `page_id`, does not overwrite prompt
- `tsu generate --profile func` — uses `.tsu/generate-func.md` prompt, writes `.tsu/document-func.md`
- `tsu generate --profile func` with `page_id` in `confluence-func.json` → syncs with the func profile's Confluence page
- `tsu push --profile func` — pushes `.tsu/document-func.md` to the page configured in `.tsu/confluence-func.json`
- `tsu generate --profile nonexistent` → clear error: "Profile 'nonexistent' not found. Run `tsu init --profile nonexistent` first."
- `tsu generate` (no `--profile`) → uses tech profile, identical to pre-profile behavior
- Existing `.tsu/` directories without profiles continue working unchanged

### Automated Test Suite

All external services (Confluence REST API, GitHub Copilot SDK, system keychain) are mocked. No network calls. Tests run locally with `pytest`.

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures (tmp_project, mock_keyring, cli_runner, etc.)
├── test_confluence_utils.py # URL parsing + mocked API resolution
├── test_config.py           # Config I/O, filenames, profiles, seed_prompt
├── test_auth.py             # Credential resolution chain (env → keyring → prompt)
├── test_publisher.py        # Markdown conversion, headers, mocked API calls, push flow
├── test_generator.py        # Model validation, mocked CopilotClient generation
└── test_cli.py              # Typer CliRunner E2E tests for all commands
```

**Running tests:**

```bash
pip install -e ".[dev]"       # Install with test dependencies
pytest -v                     # Run all tests
pytest --cov=src --cov-report=term-missing  # With coverage
pytest tests/test_config.py   # Single module
```

#### Unit Tests — Pure Functions

**`tests/test_confluence_utils.py`** — URL parsing (no mocks needed)

| # | Test | What it verifies |
|---|------|------------------|
| 1 | `test_extract_base_url_cloud` | Cloud URLs (`https://x.atlassian.net/wiki/...`) → `https://x.atlassian.net/wiki` |
| 2 | `test_extract_base_url_server` | Server URLs without `/wiki` prefix → scheme + host only |
| 3 | `test_extract_base_url_trailing_slash` | Trailing slashes stripped |
| 4 | `test_extract_page_id_query_param` | `?pageId=123` → `"123"` |
| 5 | `test_extract_page_id_path` | `/pages/123/Title` → `"123"` |
| 6 | `test_extract_page_id_none` | No page ID in URL → `None` |
| 7 | `test_extract_space_and_title` | `/display/SPACE/My+Title` → `("SPACE", "My Title")` |
| 8 | `test_extract_space_and_title_missing` | Non-display URL → `(None, None)` |
| 9 | `test_extract_space_key_spaces_format` | `/spaces/KEY/pages/...` → `"KEY"` |
| 10 | `test_extract_space_key_display_format` | `/display/KEY/Title` → `"KEY"` |
| 11 | `test_extract_space_key_none` | No space key in URL → `None` |

**`tests/test_config.py`** — Config I/O and profile file naming

| # | Test | What it verifies |
|---|------|------------------|
| 12 | `test_confluence_filename_default` | `_confluence_filename("tech")` → `"confluence.json"` (legacy) |
| 13 | `test_confluence_filename_custom` | `_confluence_filename("ops")` → `"confluence-ops.json"` |
| 14 | `test_prompt_filename_default` | `_prompt_filename("tech")` → `"generate.md"` |
| 15 | `test_prompt_filename_custom` | `_prompt_filename("func")` → `"generate-func.md"` |
| 16 | `test_document_filename_default` | `_document_filename("tech")` → `"document.md"` |
| 17 | `test_document_filename_custom` | `_document_filename("api")` → `"document-api.md"` |
| 18 | `test_read_write_config_roundtrip` | Write then read `config.json` — data preserved |
| 19 | `test_read_config_defaults` | `read_config` on empty dir → returns `DEFAULT_CONFIG` |
| 20 | `test_read_write_confluence_roundtrip` | Write then read `confluence.json` for default profile |
| 21 | `test_read_write_confluence_custom_profile` | Write/read `confluence-ops.json` for `"ops"` profile |
| 22 | `test_list_profiles_multiple` | Seed `generate.md` + `generate-func.md` + `generate-api.md` → `["api", "func", "tech"]` |
| 23 | `test_list_profiles_empty` | No `.tsu/` → `[]` |
| 24 | `test_is_initialized_true` | With `config.json` → `True` |
| 25 | `test_is_initialized_false` | Without `config.json` → `False` |
| 26 | `test_seed_prompt_creates_file` | `seed_prompt` creates prompt file from built-in template |
| 27 | `test_seed_prompt_idempotent` | Second `seed_prompt` call doesn't overwrite edited file |
| 28 | `test_get_document_path_profile` | `get_document_path(dir, "func")` → `.tsu/document-func.md` |
| 29 | `test_get_prompt_path_profile` | `get_prompt_path(dir, "ops")` → `.tsu/generate-ops.md` |
| 30 | `test_multi_profile_isolation` | Init `tech` + `ops` profiles, writing to one doesn't affect the other |
| 31 | `test_tech_backward_compat` | `"tech"` profile always uses legacy names (no `-tech` suffix) |

**`tests/test_auth.py`** — Credential resolution (mock keyring + env)

| # | Test | What it verifies |
|---|------|------------------|
| 32 | `test_get_token_env_var` | `CONFLUENCE_TOKEN` set → returns env value |
| 33 | `test_get_token_keyring` | No env var, keyring has value → returns keyring value |
| 34 | `test_get_token_missing_no_prompt` | Both absent + `prompt_if_missing=False` → `None` |
| 35 | `test_get_user_env_var` | `CONFLUENCE_USER` set → returns env value |
| 36 | `test_get_user_keyring` | No env var, keyring has value → returns keyring value |
| 37 | `test_get_user_missing_no_prompt` | Both absent + `prompt_if_missing=False` → `None` |
| 38 | `test_set_credentials` | `set_credentials` calls `keyring.set_password` correctly |
| 39 | `test_clear_credentials` | `clear_credentials` calls `keyring.delete_password` |
| 40 | `test_clear_credentials_not_found` | `clear_credentials` handles `PasswordDeleteError` gracefully |
| 41 | `test_get_status_env` | Token in env → `{"token": "env", ...}` |
| 42 | `test_get_status_keyring` | Token in keyring → `{"token": "keyring", ...}` |
| 43 | `test_get_status_not_set` | Nothing set → `{"token": "not set", "user": "not set"}` |

**`tests/test_publisher.py`** — Markdown conversion + header builder

| # | Test | What it verifies |
|---|------|------------------|
| 44 | `test_markdown_to_confluence_headings` | `# H1` → `<h1>H1</h1>` |
| 45 | `test_markdown_to_confluence_code` | Fenced code blocks → `<pre><code>` |
| 46 | `test_build_headers` | Returns `Authorization: Bearer ...`, `Content-Type`, `Accept` |

**`tests/test_generator.py`** — Model validation

| # | Test | What it verifies |
|---|------|------------------|
| 47 | `test_validate_model_match` | `"gpt-4o"` in `["gpt-4o", "claude-sonnet-4.5"]` → `True` |
| 48 | `test_validate_model_case_insensitive` | `"GPT-4O"` matches `"gpt-4o"` → `True` |
| 49 | `test_validate_model_missing` | `"unknown"` → `False` |
| 50 | `test_validate_model_empty_list` | Empty available list → `True` (can't validate) |

#### Integration Tests — Mocked External Services

**`tests/test_confluence_utils.py`** — API-dependent resolution (mock httpx)

| # | Test | What it verifies |
|---|------|------------------|
| 51 | `test_get_page_id_by_space_and_title` | Mock search API → returns page ID |
| 52 | `test_get_page_id_by_space_and_title_not_found` | Empty results → raises Exception |
| 53 | `test_resolve_page_id_direct` | URL with `pageId` → resolves without API call |
| 54 | `test_resolve_page_id_via_search` | Display URL → falls back to API search |
| 55 | `test_resolve_page_id_fails` | No ID, no space/title → raises Exception |
| 56 | `test_get_space_key_from_page` | Mock API → returns space key |

**`tests/test_publisher.py`** — API calls (mock httpx + auth)

| # | Test | What it verifies |
|---|------|------------------|
| 57 | `test_get_page_found` | Mock GET 200 → returns page data dict |
| 58 | `test_get_page_not_found` | Mock GET 404 → returns `None` |
| 59 | `test_create_page_payload` | Mock POST → verifies payload has space, title, body, ancestors |
| 60 | `test_update_page_version_increment` | Mock PUT → version number incremented by 1 |
| 61 | `test_push_create_new` | No `page_id` → creates page, persists `page_id` to config |
| 62 | `test_push_update_existing` | Has `page_id` → updates page with incremented version |
| 63 | `test_push_page_deleted_recreate` | `page_id` exists but 404 → re-creates page |
| 64 | `test_push_no_credentials` | No creds → `SystemExit(1)` |
| 65 | `test_push_no_parent_url` | Empty `parent_page_url` → `SystemExit(1)` |
| 66 | `test_fetch_page_html` | Mock API → returns HTML body |
| 67 | `test_fetch_page_html_no_page_id` | No `page_id` → raises `NoPageIDError` |
| 68 | `test_create_blank_page` | Mock resolve + create → returns new page ID |
| 69 | `test_push_profile_ops_uses_correct_files` | Profile `"ops"` reads `confluence-ops.json`, writes `page_id` back to it |

**`tests/test_generator.py`** — Copilot SDK (mock CopilotClient)

| # | Test | What it verifies |
|---|------|------------------|
| 70 | `test_list_models` | Mock CopilotClient → returns model list |
| 71 | `test_generate_writes_document` | Mock CopilotClient → output file written to `get_document_path` |
| 72 | `test_generate_strips_code_fences` | Response wrapped in ` ```markdown ` → fences stripped |
| 73 | `test_generate_missing_prompt` | No prompt file → `SystemExit(1)` |
| 74 | `test_generate_profile_uses_correct_prompt` | Profile `"ops"` → loads `generate-ops.md` (not `generate.md`) |

#### CLI End-to-End Tests (Typer CliRunner)

**`tests/test_cli.py`** — Full command invocations with mocked dependencies

| # | Test | What it verifies |
|---|------|------------------|
| 75 | `test_init_creates_tsu_dir` | `tsu init` → `.tsu/` with `config.json`, `confluence.json`, `generate.md` |
| 76 | `test_init_custom_profile` | `tsu init --profile ops` → `confluence-ops.json`, `generate-ops.md` created |
| 77 | `test_init_preserves_page_id` | Re-init with existing `page_id` → preserved in config |
| 78 | `test_init_default_page_title_tech` | `--profile tech` → title contains `"Tech Overview"` |
| 79 | `test_init_default_page_title_custom` | `--profile func` → title contains `"Func"` |
| 80 | `test_generate_offline` | `tsu generate --offline` → mock Copilot, document file created |
| 81 | `test_generate_profile_not_found` | `tsu generate --profile nonexistent` → exit code 1, error message |
| 82 | `test_push_success` | `tsu push` → mock httpx + auth, success output |
| 83 | `test_push_not_initialized` | `tsu push` without `.tsu/` → exit code 1 |
| 84 | `test_list_profiles_output` | Seed `tech` + `ops` profiles → both appear in table output |
| 85 | `test_list_profiles_multi_profile_table` | Init two profiles with different titles → correct titles shown |
| 86 | `test_models_command` | Mock Copilot SDK → model list printed |
| 87 | `test_auth_set` | Mock `typer.prompt` + keyring → credentials stored |
| 88 | `test_auth_clear` | Mock confirm + keyring → credentials removed |
| 89 | `test_auth_status` | Mock `get_status` → formatted table output |
| 90 | `test_generate_not_initialized` | `tsu generate` without `.tsu/` → abort |

#### Design Decisions

- **No CI** — local `pytest` only
- **Mocking** — `unittest.mock.patch` (stdlib) — no extra dependencies
- **Async tests** — `pytest-asyncio` with `asyncio_mode = "auto"`
- **File I/O** — pytest's `tmp_path` fixture for real filesystem operations (config, seed_prompt, generate output)
- **Coverage** — `pytest-cov` added to dev dependencies

## Key Decisions

- **Single generate step:** Merged scan + generate into one Copilot session for simplicity.
- **Sync-by-default:** `tsu generate` pulls the existing Confluence page and sends it to the LLM as reference context, preserving manual edits. Gracefully degrades (no `page_id`, no creds, API failure → fresh generation). `--offline` to opt out.
- **Raw HTML, no conversion:** Existing page content is passed as Confluence storage-format HTML directly to the LLM — no `markdownify` dependency, no lossy round-trip. The LLM reads the HTML and still outputs markdown.
- **Prompts as external templates:** `.md` + Jinja2 — readable, editable. Seeded into `.tsu/` during init for direct user editing.
- **`httpx` over `requests`:** Consistent with the async-native Copilot SDK.
- **Direct REST over wrapper libraries:** Only 3 Confluence endpoints needed.
- **`.tsu/` fully git-tracked:** No sensitive data → no gitignore gymnastics needed.
- **Two config files:** `config.json` (tool settings) vs `confluence.json` (page target) — clean separation.
- **Mermaid theme in prompt:** Greyscale enforced at generation time, not post-processed.
- **Confluence Mermaid macro configurable:** `mermaid_macro` field in `confluence.json` to match the user's installed plugin.
- **Python 3.11+** required (Copilot SDK requirement).
- **Copilot CLI** must be installed and authenticated separately.
- **Profile-based multi-document support:** Each profile gets its own prompt template, Confluence page, and output file. Enables generating different document types (tech, functional rules, business rules, etc.) from the same codebase without separate commands or tooling.
- **Backward compat via filename convention:** The `tech` profile uses legacy filenames (`generate.md`, `document.md`, `confluence.json`) with no `-tech` suffix, so existing `.tsu/` directories work without migration. Custom profiles use `-{profile}` suffix.
- **Default to `tech` profile:** Omitting `--profile` always uses `tech`, preserving current behavior exactly.
- **Single prompt template as seed:** `src/prompts/generate.md` is the only built-in prompt. All profiles — including custom ones — are seeded from it. Users edit the seeded copy to adapt it to their document type. No separate base template needed.
- **Profiles are per-project:** Stored in `.tsu/` alongside the project, not in global config. Different projects can have different sets of profiles.
- **Profile init is additive:** `tsu init --profile func` only adds the new profile's files without touching existing config or other profiles.
