"""Diff engine for tsu-cli.

Gathers change context (git diff or remote page comparison) and runs
the Copilot agent with a dedicated diff prompt to produce a structured
change report (What's Stale / What's New / What's Wrong).
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

from copilot import CopilotClient, PermissionRequestResult

try:
    from copilot.types import SubprocessConfig as _SubprocessConfig
except ImportError:
    _SubprocessConfig = None

from jinja2 import Template

from tsu_cli.config import (
    TSU_DIR,
    DEFAULT_PROFILE,
    _document_filename,
    get_document_path,
    read_config,
    safe_write_text,
    validate_write_path,
)

console = Console()

# Maximum characters of git diff output to inject into the prompt.
# Beyond this we fall back to --stat and let the agent drill in via shell.
_MAX_DIFF_CHARS = 80_000


def _diff_output_filename(profile: str) -> str:
    """Return the diff report filename for a profile."""
    if profile == DEFAULT_PROFILE:
        return "diff.md"
    return f"diff-{profile}.md"


def get_diff_output_path(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Return the diff report output path for *profile*."""
    base = project_dir or Path.cwd()
    return base / TSU_DIR / _diff_output_filename(profile)


# -------------------------------------------------------------------
# Change context gathering
# -------------------------------------------------------------------


def _check_git_available(project_dir: Path) -> None:
    """Raise RuntimeError if git is not available or not a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Not a git repository: {project_dir}\n"
                "The 'tsu diff' command requires a git repository "
                "for code diff mode. Use 'tsu diff --remote' to compare "
                "against the Confluence page instead."
            )
    except FileNotFoundError:
        raise RuntimeError(
            "git is not installed or not in PATH.\n"
            "The 'tsu diff' command requires git for code diff mode. "
            "Use 'tsu diff --remote' to compare against the Confluence "
            "page instead."
        )


def get_git_diff(project_dir: Path, ref: str = "HEAD") -> str:
    """Run ``git diff`` and return the output as a string.

    If the full diff exceeds ``_MAX_DIFF_CHARS``, returns a stat summary
    with a note that the agent should use shell access for details.

    Args:
        project_dir: Root of the git repository.
        ref: Git ref to diff against (e.g. ``HEAD``, ``HEAD~3``, ``main``).

    Returns:
        Formatted string with the git diff context.

    Raises:
        RuntimeError: If git is not available or not a git repo.
    """
    _check_git_available(project_dir)

    # Get the full diff
    result = subprocess.run(
        ["git", "diff", ref],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    full_diff = result.stdout

    # Also get the stat summary
    stat_result = subprocess.run(
        ["git", "diff", "--stat", ref],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    stat = stat_result.stdout.strip()

    if not full_diff.strip() and not stat:
        return (
            "No code changes detected with `git diff " + ref + "`.\n"
            "You may want to try a different ref (e.g. HEAD~1, main)."
        )

    header = f"Git diff against `{ref}`:\n\n"

    if len(full_diff) <= _MAX_DIFF_CHARS:
        return (
            header
            + "### Summary\n```\n" + stat + "\n```\n\n"
            + "### Full Diff\n```diff\n" + full_diff.strip() + "\n```"
        )

    # Diff too large — provide stat only, agent can drill in
    return (
        header
        + "### Summary\n```\n" + stat + "\n```\n\n"
        + "**Note:** The full diff is too large to include inline. "
        "Use `git diff " + ref + " -- <file>` via shell to inspect "
        "specific files."
    )


def get_remote_diff(project_dir: Path, profile: str = DEFAULT_PROFILE) -> str:
    """Fetch the live Confluence page and return its markdown for comparison.

    Args:
        project_dir: Project root directory.
        profile: Document profile name.

    Returns:
        Formatted string with the remote page context.

    Raises:
        RuntimeError: If the page cannot be fetched.
    """
    from tsu_cli.publisher import fetch_page_html, html_to_markdown

    html = fetch_page_html(project_dir, profile)
    if not html:
        raise RuntimeError("Remote page returned empty content")

    remote_md = html_to_markdown(html)

    return (
        "The following is the **live Confluence page** content (converted to markdown).\n"
        "Compare this against the local documentation in "
        f"`.tsu/{_document_filename(profile)}` to identify discrepancies.\n\n"
        "### Remote Page Content\n\n" + remote_md
    )


# -------------------------------------------------------------------
# Diff agent execution
# -------------------------------------------------------------------


def _make_diff_permission_handler(project_dir: Path):
    """Permission handler for the diff agent — same restrictions as generate."""

    def handler(request, _invocation=None):  # noqa: ANN001
        kind = request.kind if isinstance(request.kind, str) else request.kind.value

        if kind == "write":
            try:
                validate_write_path(Path(request.file_name), project_dir)
                return PermissionRequestResult(kind="approved")
            except (ValueError, OSError):
                return PermissionRequestResult(kind="denied-by-rules")

        return PermissionRequestResult(kind="approved")

    return handler


async def _run_diff(
    project_dir: Path,
    change_context: str,
    model: str | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Run the Copilot agent with the diff prompt to produce a change report.

    Args:
        project_dir: Root directory of the project.
        change_context: Pre-gathered change context (git diff or remote content).
        model: LLM model to use (overrides config).
        profile: Document profile name.

    Returns:
        Path to the generated diff report.
    """
    cfg = read_config(project_dir)
    model = model or cfg.get("model", "auto")
    output_path = get_diff_output_path(project_dir, profile)

    # Load the diff system prompt
    from importlib import resources

    system_text = (
        resources.files("tsu_cli.prompts") / "diff.md"
    ).read_text(encoding="utf-8")

    # Render the prompt template
    prompt = Template(
        system_text,
        keep_trailing_newline=True,
    ).render(
        change_context=change_context,
        document_filename=_document_filename(profile),
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

    # Start Copilot client
    if _SubprocessConfig is not None:
        client = CopilotClient(_SubprocessConfig(cwd=str(project_dir)))
    else:
        client = CopilotClient({"cwd": str(project_dir)})
    await client.start()

    try:
        try:
            session_ctx = await client.create_session(
                model=model,
                on_permission_request=_make_diff_permission_handler(project_dir),
            )
        except TypeError:
            session_ctx = await client.create_session({
                "model": model,
                "on_permission_request": _make_diff_permission_handler(project_dir),
            })
        async with session_ctx as session:
            session.on(on_event)

            console.print(f"[dim]Model:[/dim] {model}")
            console.print(f"[dim]Project:[/dim] {project_dir}")
            if profile != DEFAULT_PROFILE:
                console.print(f"[dim]Profile:[/dim] {profile}")
            console.print()

            with Live(Spinner("dots", text="Analyzing changes..."), console=console):
                await session.send({"prompt": prompt})
                await done.wait()

    finally:
        await client.stop()

    if not response_content:
        console.print("[red]Error:[/red] No response received from Copilot agent.")
        raise SystemExit(1)

    # Strip wrapping code fences
    content = response_content.strip()
    if content.startswith("```markdown"):
        content = content[len("```markdown"):].strip()
    if content.startswith("```md"):
        content = content[len("```md"):].strip()
    if content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    # Write the report
    safe_write_text(output_path, content + "\n", project_dir)

    # Print summary to terminal
    console.print()
    console.print(f"[green]✓[/green] Diff report generated: {output_path}")

    # Print a condensed version to terminal
    lines = content.splitlines()
    for line in lines:
        if line.startswith("## "):
            console.print(f"\n[bold]{line}[/bold]")
        elif line.strip():
            console.print(f"  {line}")

    return output_path


def run_diff(
    project_dir: Path,
    change_context: str,
    model: str | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Synchronous wrapper for the async diff process.

    Args:
        project_dir: Root directory of the project.
        change_context: Pre-gathered change context.
        model: LLM model override.
        profile: Document profile name.

    Returns:
        Path to the generated diff report.
    """
    return asyncio.run(
        _run_diff(project_dir, change_context, model, profile)
    )
