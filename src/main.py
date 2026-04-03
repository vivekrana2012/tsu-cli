"""tsu-cli: Generate project tech documentation and push to Confluence.

Commands:
    tsu init       — Interactive setup, creates .tsu/ config directory
    tsu generate   — Analyze project with Copilot and produce document.md
    tsu push       — Upload document.md to Confluence
    tsu auth set   — Store Confluence credentials in system keychain
    tsu auth clear — Remove stored credentials
    tsu auth status — Show credential configuration status
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tsu_cli.publisher import NoPageIDError, NoCredentialsError, NoParentPageError
import typer
from rich.console import Console
from rich.table import Table

from tsu_cli import __version__, auth, config, generator, publisher
from tsu_cli.config import DEFAULT_PROFILE

console = Console()


app = typer.Typer(
    name="tsu",
    help=f"tsu-cli — Generate project tech documentation and push to Confluence.\n\nRun [bold]tsu help[/bold] for a detailed usage guide.",
    no_args_is_help=False,
    rich_markup_mode="rich",
    epilog="[dim]Run [bold]tsu help[/bold] for a detailed usage guide.[/dim]",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show version and exit.", is_eager=True),
) -> None:
    if version:
        console.print(f"tsu-cli {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(f"[bold]tsu-cli[/bold] v{__version__}\n")
        console.print(ctx.get_help())
        raise typer.Exit()

auth_app = typer.Typer(
    name="auth",
    help="Manage Confluence authentication credentials.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


# ---------------------------------------------------------------------------
# tsu list-profiles
# ---------------------------------------------------------------------------


@app.command("profiles")
def profiles_command(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
) -> None:
    """List initialized profiles and available built-in templates."""
    project_dir = project_dir or Path.cwd()

    initialized = config.is_initialized(project_dir)
    profiles = config.list_profiles(project_dir) if initialized else []
    builtin = config.list_builtin_templates()

    # --- Initialized profiles ---
    if profiles:
        table = Table(title="Initialized")
        table.add_column("Profile", style="bold")
        table.add_column("Prompt")
        table.add_column("Confluence Page")
        table.add_column("Page ID")

        for p in profiles:
            prompt_file = config._prompt_filename(p)
            conf = config.read_confluence(project_dir, p)
            page_title = conf.get("page_title", "") or "[dim]—[/dim]"
            page_id = conf.get("page_id") or "[dim]—[/dim]"
            table.add_row(p, prompt_file, page_title, str(page_id))

        console.print()
        console.print(table)
    else:
        console.print("\n[yellow]No initialized profiles.[/yellow] Run [bold]tsu init[/bold] to get started.")

    # --- Available built-in templates (not yet initialized) ---
    available = {k: v for k, v in builtin.items() if k not in profiles}
    if available:
        avail_table = Table(title="Available Templates")
        avail_table.add_column("Profile", style="bold")
        avail_table.add_column("Description")

        for name, desc in available.items():
            avail_table.add_row(name, desc)

        console.print()
        console.print(avail_table)
        console.print("\n[dim]Run [bold]tsu init --profile <name>[/bold] to initialize a template.[/dim]")

    console.print()


# ---------------------------------------------------------------------------
# tsu models
# ---------------------------------------------------------------------------


@app.command("models")
def models_command() -> None:
    """List available LLM models from the Copilot SDK."""
    console.print("\n[bold]Available Models[/bold]\n")
    available = generator.list_models()
    if not available:
        console.print("[yellow]Could not retrieve model list from Copilot SDK.[/yellow]")
        raise SystemExit(1)
    for m in available:
        console.print(f"  • {m}")
    console.print()


# ---------------------------------------------------------------------------
# tsu init
# ---------------------------------------------------------------------------


@app.command()
def init(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE,
        "--profile", "-p",
        help="Document profile to initialize (e.g. tech, func, api).",
    ),
) -> None:
    """Initialize tsu-cli in the current project directory.

    Creates .tsu/config.json and profile-specific files (prompt template,
    confluence config) with interactive prompts.
    """
    project_dir = project_dir or Path.cwd()
    tsu_dir = config.get_tsu_dir(project_dir)

    existing_page_id: str | None = None
    already_initialized = config.is_initialized(project_dir)

    if already_initialized:
        # Preserve existing page_id for this profile so re-init doesn't create duplicates
        existing_page_id = config.read_confluence(project_dir, profile).get("page_id")

        # For the default tech profile, ask before overwriting
        if profile == DEFAULT_PROFILE:
            if not typer.confirm(f".tsu/ already exists at {tsu_dir}. Overwrite?", default=False):
                raise typer.Abort()
        else:
            # For non-default profiles, check if the profile already exists
            prompt_path = config.get_prompt_path(project_dir, profile)
            if prompt_path.exists():
                if not typer.confirm(f"Profile '{profile}' already exists. Overwrite?", default=False):
                    raise typer.Abort()

    console.print(f"\n[bold]tsu init[/bold] — Project documentation setup (profile: {profile})\n")

    # --- Tool config (only on first init or tech profile overwrite) ---
    if not already_initialized:
        console.print("[bold]Tool Configuration[/bold]")

        # Show available models as a hint
        available_models = generator.list_models()
        if available_models:
            console.print("[dim]Available models:[/dim]")
            for m in available_models:
                console.print(f"  [dim]• {m}[/dim]")
            console.print()

        model = typer.prompt("LLM model", default="auto")

        if available_models and not generator.validate_model(model, available_models):
            console.print(f"[yellow]Warning:[/yellow] '{model}' is not in the available models list. Using Auto.")

        config_data = {
            "model": model,
        }

        config_path = config.write_config(config_data, project_dir)
        console.print(f"[green]✓[/green] Created {config_path}")

    # --- Confluence config (per profile) ---
    console.print("\n[bold]Confluence Configuration[/bold]")
    console.print("[dim]Press Enter to skip fields if you only need markdown generation.[/dim]\n")

    default_title = f"{project_dir.name} - Tech Overview"
    if profile != DEFAULT_PROFILE:
        default_title = f"{project_dir.name} - {profile.capitalize()}"

    parent_page_url = typer.prompt(
        "Parent page URL (paste full Confluence page URL, or leave empty)",
        default="",
    )

    page_title = typer.prompt("Page title", default=default_title) if parent_page_url else default_title

    confluence_data = {
        "parent_page_url": parent_page_url,
        "page_title": page_title,
        "page_id": existing_page_id,  # preserve from previous init if present
    }

    confluence_path = config.write_confluence(confluence_data, project_dir, profile)
    console.print(f"[green]✓[/green] Created {confluence_path}")

    # --- Seed prompt template ---
    prompt_path = config.seed_prompt(project_dir, profile)
    console.print(f"[green]✓[/green] Created {prompt_path}")

    # --- Confluence auth (optional, shared across profiles) ---
    if parent_page_url:
        console.print("\n[bold]Confluence Credentials[/bold]")
        console.print("[dim]Stored in your system keychain, not in config files.[/dim]\n")

        if typer.confirm("Set up Confluence credentials now?", default=True):
            user = typer.prompt("Confluence user email")
            token = typer.prompt("Confluence API token", hide_input=True)
            auth.set_credentials(user, token)
            console.print("[green]✓[/green] Credentials stored in keychain")

        # --- Create blank Confluence page (if needed) ---
        if not existing_page_id:
            token = auth.get_token(prompt_if_missing=False)
            if token:
                console.print("\n[bold]Creating blank Confluence page...[/bold]")
                try:
                    new_page_id = publisher.create_blank_page(parent_page_url, page_title)
                    confluence_data["page_id"] = new_page_id
                    config.write_confluence(confluence_data, project_dir, profile)
                    console.print(f"[green]✓[/green] Created blank page (page_id: {new_page_id})")
                except Exception as exc:  # noqa: BLE001
                    console.print(
                        f"[yellow]Warning:[/yellow] Could not create blank page: {exc}\n"
                        "[dim]You can still push later to create the page.[/dim]"
                    )
                    raise typer.Abort()
            else:
                console.print(
                    "\n[dim]Skipping blank page creation (no credentials available).[/dim]"
                )
        elif existing_page_id:
            console.print(f"\n[dim]Keeping existing page_id: {existing_page_id}[/dim]")

    console.print(f"\n[green]✓[/green] tsu initialized in {tsu_dir} (profile: {profile})")
    console.print("\nNext steps:")
    if profile != DEFAULT_PROFILE:
        console.print(f"  [bold]vim .tsu/{config._prompt_filename(profile)}[/bold]  — Customize the prompt for your '{profile}' document")
    console.print(f"  [bold]tsu generate --profile {profile}[/bold]  — Analyze this project and generate documentation")
    console.print(f"  [bold]tsu push --profile {profile}[/bold]      — Upload documentation to Confluence")
    console.print(f"\n[dim]Tip: Edit .tsu/{config._prompt_filename(profile)} to customize the generation prompt.[/dim]")


# ---------------------------------------------------------------------------
# tsu generate
# ---------------------------------------------------------------------------


@app.command()
def generate(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
    model: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--model", "-m",
        help="LLM model override (e.g. gpt-4o, claude-sonnet-4.5).",
    ),
    output: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--output", "-o",
        help="Output file path override.",
    ),
    extra_instructions: str = typer.Option(
        "",
        "--extra", "-e",
        help="Additional instructions to append to the prompt.",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Skip syncing with Confluence and generate from codebase only.",
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE,
        "--profile", "-p",
        help="Document profile to generate (e.g. tech, func, api).",
    ),
) -> None:
    """Analyze the current project with GitHub Copilot and generate documentation.

    Uses the Copilot SDK agent to explore the project directory, identify
    the tech stack, architecture, APIs, and dependencies, then produces a
    comprehensive markdown document.

    By default, if a Confluence page already exists (page_id in the profile's
    confluence config) and credentials are available, the current page content
    is pulled and saved as local markdown before generation so the agent can
    update it incrementally. Use --offline to skip this.
    """
    project_dir = project_dir or Path.cwd()

    if not config.is_initialized(project_dir):
        console.print(
            "[yellow]Warning:[/yellow] .tsu/ not initialized. "
            "Run 'tsu init' first, or using defaults."
        )
        raise typer.Abort()

    # Validate that the profile is initialized
    prompt_path = config.get_prompt_path(project_dir, profile)
    if not prompt_path.exists():
        console.print(
            f"[red]Error:[/red] Profile '{profile}' not found. "
            f"Run [bold]tsu init --profile {profile}[/bold] first."
        )
        raise SystemExit(1)


    # Sync with Confluence (pull existing page as local markdown)
    if not offline:
        confluence_conf = config.read_confluence(project_dir, profile)
        has_page_id = bool(confluence_conf.get("page_id"))

        if has_page_id:
            # page_id exists → pull is mandatory to avoid overwriting remote edits
            console.print("[dim]Syncing with Confluence page...[/dim]")
            try:
                doc_path = publisher.pull(project_dir, profile)
                console.print(f"[dim]✓ Remote page synced to {doc_path.name}[/dim]")
            except Exception as ex:
                console.print(f"[red]Error:[/red] Failed to sync Confluence page: {ex}")
                console.print(
                    "[dim]Use [bold]tsu generate --offline[/bold] to skip sync "
                    "and generate fresh.[/dim]"
                )
                raise SystemExit(1)
        else:
            console.print("[dim]No existing Confluence page — generating fresh[/dim]")

    else:
        console.print("[dim]Offline mode — generating fresh[/dim]")

    console.print("\n[bold]tsu generate[/bold] — Analyzing...\n")
    generator.generate(project_dir, model, output, extra_instructions, profile)


# ---------------------------------------------------------------------------
# tsu pull
# ---------------------------------------------------------------------------


@app.command()
def pull(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE,
        "--profile", "-p",
        help="Document profile to pull (e.g. tech, func, api).",
    ),
) -> None:
    """Pull the remote Confluence page and save as local markdown.

    Fetches the existing page content, converts it from Confluence storage
    HTML to markdown, and writes it to the profile's document file
    (e.g. .tsu/document.md). Overwrites any existing local file.
    """
    project_dir = project_dir or Path.cwd()

    if not config.is_initialized(project_dir):
        console.print("[red]Error:[/red] .tsu/ not initialized. Run 'tsu init' first.")
        raise SystemExit(1)

    console.print(f"\n[bold]tsu pull[/bold] — Syncing remote page (profile: {profile})...\n")

    try:
        doc_path = publisher.pull(project_dir, profile)
        console.print(f"[green]✓[/green] Remote page saved to {doc_path}")
    except (NoPageIDError, NoParentPageError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)
    except NoCredentialsError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error:[/red] Failed to pull page: {exc}")
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# tsu push
# ---------------------------------------------------------------------------


@app.command()
def push(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
    profile: str = typer.Option(
        DEFAULT_PROFILE,
        "--profile", "-p",
        help="Document profile to push (e.g. tech, func, api).",
    ),
) -> None:
    """Push the generated document to Confluence.

    Creates a new page if page_id is not set in the profile's confluence
    config, or updates the existing page if it is. On first push, the
    page_id is written back to the config for future updates.
    """
    project_dir = project_dir or Path.cwd()

    if not config.is_initialized(project_dir):
        console.print("[red]Error:[/red] .tsu/ not initialized. Run 'tsu init' first.")
        raise SystemExit(1)

    confluence_config = config.read_confluence(project_dir, profile)
    if not confluence_config.get("parent_page_url"):
        console.print(
            "[red]Error:[/red] Parent page URL not configured for "
            f"profile '{profile}'. Run 'tsu init --profile {profile}' "
            "and provide Confluence details."
        )
        raise SystemExit(1)

    console.print(f"\n[bold]tsu push[/bold] — Uploading to Confluence (profile: {profile})...\n")
    publisher.push(project_dir, profile)


# ---------------------------------------------------------------------------
# tsu auth set
# ---------------------------------------------------------------------------


@auth_app.command("set")
def auth_set() -> None:
    """Store Confluence credentials in the system keychain."""
    console.print("\n[bold]tsu auth set[/bold]\n")
    user = typer.prompt("Confluence user email")
    token = typer.prompt("Confluence API token", hide_input=True)
    auth.set_credentials(user, token)
    console.print("[green]✓[/green] Credentials stored in keychain")


# ---------------------------------------------------------------------------
# tsu auth clear
# ---------------------------------------------------------------------------


@auth_app.command("clear")
def auth_clear() -> None:
    """Remove Confluence credentials from the system keychain."""
    if typer.confirm("Remove stored Confluence credentials?", default=False):
        auth.clear_credentials()
        console.print("[green]✓[/green] Credentials removed from keychain")


# ---------------------------------------------------------------------------
# tsu auth status
# ---------------------------------------------------------------------------


@auth_app.command("status")
def auth_status() -> None:
    """Show where Confluence credentials are configured."""
    status = auth.get_status()

    table = Table(title="Confluence Credentials")
    table.add_column("Credential", style="bold")
    table.add_column("Source")
    table.add_column("Status")

    for name, source in [("User email", status["user"]), ("API token", status["token"])]:
        if source == "env":
            style = "green"
            status_text = "✓ Set via environment variable"
        elif source == "keyring":
            style = "green"
            status_text = "✓ Stored in system keychain"
        else:
            style = "red"
            status_text = "✗ Not configured"
        table.add_row(name, f"[{style}]{source}[/{style}]", status_text)

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# tsu help
# ---------------------------------------------------------------------------


@app.command("help", hidden=True)
def help_command() -> None:
    """Show a detailed guide for using tsu-cli."""
    from importlib import resources

    from rich.markdown import Markdown

    content = (resources.files("tsu_cli") / "help.md").read_text(encoding="utf-8")
    console.print(Markdown(content))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
