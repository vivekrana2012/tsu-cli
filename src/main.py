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

from tsu_cli.publisher import NoPageIDError
import typer
from rich.console import Console
from rich.table import Table

from tsu_cli import auth, config, generator, publisher
from tsu_cli.config import DEFAULT_PROFILE

console = Console()

app = typer.Typer(
    name="tsu",
    help="Generate project tech documentation and push to Confluence.\n\nRun [bold]tsu help[/bold] for a detailed usage guide.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    epilog="[dim]Run [bold]tsu help[/bold] for a detailed usage guide.[/dim]",
)

auth_app = typer.Typer(
    name="auth",
    help="Manage Confluence authentication credentials.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


# ---------------------------------------------------------------------------
# tsu list-profiles
# ---------------------------------------------------------------------------


@app.command("list-profiles")
def list_profiles_command(
    project_dir: Optional[Path] = typer.Option(  # noqa: UP007
        None,
        "--dir", "-d",
        help="Project directory (defaults to current directory).",
    ),
) -> None:
    """List all configured document profiles."""
    project_dir = project_dir or Path.cwd()

    if not config.is_initialized(project_dir):
        console.print("[red]Error:[/red] .tsu/ not initialized. Run 'tsu init' first.")
        raise SystemExit(1)

    profiles = config.list_profiles(project_dir)
    if not profiles:
        console.print("[yellow]No profiles found.[/yellow]")
        raise SystemExit(0)

    table = Table(title="Configured Profiles")
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
    is pulled and sent to the LLM as reference so that manually added content
    is preserved. Use --offline to skip this.
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


    # Sync with Confluence (pull existing page as reference context)
    existing_html = ""
    if not offline:
        console.print("[dim]Syncing with Confluence page...[/dim]")

        try:
            existing_html = publisher.fetch_page_html(project_dir, profile) or ""
            if existing_html:
                console.print("[dim]✓ Existing page content loaded as reference[/dim]")
            
        except NoPageIDError as ex:
            console.print("[dim] No existing page found [/dim]")
        except Exception as ex:
            console.print(f"[red]  ↳ Not able to get page: {ex}[/red]")
            raise typer.Abort()

    else:
        console.print("[dim]Offline mode — generating fresh[/dim]")

    console.print("\n[bold]tsu generate[/bold] — Analyzing project...\n")
    generator.generate(project_dir, model, output, extra_instructions, existing_html, profile)


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
