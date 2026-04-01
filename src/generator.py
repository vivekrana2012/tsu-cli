"""Project analysis and document generation using GitHub Copilot SDK.

Uses the Copilot CLI agent to autonomously explore a project directory
and produce a tech documentation markdown file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

from copilot import CopilotClient, PermissionHandler

from jinja2 import Template

from tsu_cli.config import get_document_path, get_prompt_path, read_config, DEFAULT_PROFILE

console = Console()


async def _list_models() -> list[str]:
    """Fetch available model names from the Copilot SDK.

    Returns a list of model ID strings, or an empty list if the
    SDK call fails or is not supported.
    """
    client = CopilotClient()
    await client.start()
    try:
        models = await client.list_models()
        # Handle both list-of-strings and list-of-objects with an 'id' field
        if models and isinstance(models[0], str):
            return list(models)
        return [getattr(m, "id", None) or getattr(m, "name", str(m)) for m in models]
    except Exception:  # noqa: BLE001
        return []
    finally:
        await client.stop()


def list_models() -> list[str]:
    """Synchronous wrapper — return available model names."""
    with Live(Spinner("dots", text="Fetching available models..."), console=console):
        return asyncio.run(_list_models())


def validate_model(model: str, available: list[str]) -> bool:
    """Check if *model* is in the available list (case-insensitive)."""
    if not available:
        return True  # can't validate — assume OK
    lower = {m.lower() for m in available}
    return model.lower() in lower


async def _run_generation(
    project_dir: Path,
    model: str | None = None,
    output: Path | None = None,
    extra_instructions: str = "",
    existing_html: str = "",
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Run the Copilot agent to analyze the project and generate documentation.

    Args:
        project_dir: Root directory of the project to analyze.
        model: LLM model to use (overrides config).
        output: Output file path (overrides config).
        extra_instructions: Additional instructions appended to the prompt.
        existing_html: Existing Confluence page HTML to use as reference context.
        profile: Document profile name.

    Returns:
        Path to the generated document.
    """
    config = read_config(project_dir)
    model = model or config.get("model", "auto")
    output_path = output or get_document_path(project_dir, profile)

    # # Validate model against available models
    # available = await _list_models()
    # if available and not validate_model(model, available):
    #     console.print(
    #         f"[red]Error:[/red] Unknown model [bold]{model}[/bold].\n"
    #     )
    #     console.print("[dim]Available models:[/dim]")
    #     for m in available:
    #         console.print(f"  • {m}")
    #     raise SystemExit(1)

    # Build the additional instructions block
    additional = ""
    if extra_instructions:
        additional = f"\n# Additional Instructions\n\n{extra_instructions}\n"

    # Load and render the prompt template from .tsu/generate.md (or profile variant)
    prompt_path = get_prompt_path(project_dir, profile)
    if not prompt_path.exists():
        console.print(
            "[red]Error:[/red] Prompt template not found at "
            f"{prompt_path}\nRun [bold]tsu init --profile {profile}[/bold] first."
        )
        raise SystemExit(1)
    prompt = Template(
        prompt_path.read_text(encoding="utf-8"),
        keep_trailing_newline=True,
    ).render(
        additional_instructions=additional,
        existing_document=existing_html,
    )

    # Collect the final response
    response_content: str = ""
    done = asyncio.Event()

    def on_event(event):
        nonlocal response_content
        if event.type.value == "assistant.message":
            response_content = event.data.content
        elif event.type.value == "session.idle":
            done.set()

    # Start Copilot client with cwd set to project directory
    client = CopilotClient({"cwd": str(project_dir)})
    await client.start()

    try:
        async with await client.create_session({
            "model": model,
            "on_permission_request": PermissionHandler.approve_all,
        }) as session:
            session.on(on_event)

            console.print(f"[dim]Model:[/dim] {model}")
            console.print(f"[dim]Project:[/dim] {project_dir}")
            if profile != DEFAULT_PROFILE:
                console.print(f"[dim]Profile:[/dim] {profile}")
            console.print()

            with Live(Spinner("dots", text="Analyzing project..."), console=console):
                await session.send({"prompt": prompt})
                await done.wait()

    finally:
        await client.stop()

    if not response_content:
        console.print("[red]Error:[/red] No response received from Copilot agent.")
        raise SystemExit(1)

    # Strip any wrapping code fences the model may have added
    content = response_content.strip()
    if content.startswith("```markdown"):
        content = content[len("```markdown") :].strip()
    if content.startswith("```md"):
        content = content[len("```md") :].strip()
    if content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    # Write the document
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content + "\n", encoding="utf-8")

    # Summary
    lines = content.splitlines()
    sections = [l for l in lines if l.startswith("## ")]
    word_count = len(content.split())

    console.print()
    console.print(f"[green]✓[/green] Document generated: {output_path}")
    console.print(f"  [dim]Sections:[/dim] {len(sections)}")
    console.print(f"  [dim]Words:[/dim]    {word_count}")
    console.print(f"  [dim]Lines:[/dim]    {len(lines)}")

    return output_path


def generate(
    project_dir: Path | None = None,
    model: str | None = None,
    output: Path | None = None,
    extra_instructions: str = "",
    existing_html: str = "",
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Synchronous wrapper for the async generation process.

    Args:
        project_dir: Root directory of the project to analyze (defaults to cwd).
        model: LLM model override.
        output: Output file path override.
        extra_instructions: Extra instructions for the prompt.
        existing_html: Existing Confluence page HTML to use as reference context.
        profile: Document profile name.

    Returns:
        Path to the generated document.
    """
    project_dir = project_dir or Path.cwd()
    return asyncio.run(
        _run_generation(project_dir, model, output, extra_instructions, existing_html, profile)
    )
