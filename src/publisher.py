"""Confluence publisher for tsu-cli.

Handles uploading document.md to Confluence via direct REST API calls using httpx.
Supports creating new pages and updating existing ones.
Converts markdown to Confluence storage format (XHTML).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import markdown as md
from rich.console import Console

from tsu_cli import auth, config
from tsu_cli.config import DEFAULT_PROFILE
from tsu_cli.confluence_utils import (
    extract_base_url,
    extract_space_key_from_url,
    get_space_key_from_page,
    resolve_page_id,
)


class NoPageIDError(Exception):
    """Raised when no page_id is found in confluence.json."""


class NoParentPageError(Exception):
    """Raised when no parent_page_url is found in confluence.json."""


class NoCredentialsError(Exception):
    """Raised when no Confluence credentials are available."""

console = Console()


def _markdown_to_confluence(content: str) -> str:
    """Convert markdown content to Confluence storage format (XHTML).

    Args:
        content: Raw markdown string.

    Returns:
        Confluence storage format XHTML string.
    """
    return md.markdown(
        content,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )


def _build_headers(token: str) -> dict[str, str]:
    """Build HTTP headers with Bearer token auth.

    Matches the working Confluence publish code pattern:
    Authorization: Bearer {token} in headers on every request.
    """
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get_page(
    client: httpx.Client,
    base_url: str,
    page_id: str,
) -> dict | None:
    """Fetch an existing Confluence page by ID.

    Returns:
        Page data dict, or None if page not found (404).

    Raises:
        httpx.HTTPStatusError: For non-404 error responses.
    """
    url = f"{base_url}/rest/api/content/{page_id}"
    resp = client.get(url, params={"expand": "version"})

    if resp.status_code == 404:
        return None

    resp.raise_for_status()
    return resp.json()


def _create_page(
    client: httpx.Client,
    base_url: str,
    space_key: str,
    title: str,
    body_html: str,
    parent_page_id: str | None = None,
) -> dict:
    """Create a new Confluence page.

    Returns:
        Created page data dict from Confluence API.
    """
    url = f"{base_url}/rest/api/content"
    payload: dict = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }

    if parent_page_id:
        payload["ancestors"] = [{"id": str(parent_page_id)}]

    resp = client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def _update_page(
    client: httpx.Client,
    base_url: str,
    page_id: str,
    title: str,
    body_html: str,
    current_version: int,
) -> dict:
    """Update an existing Confluence page.

    Args:
        current_version: The current version number (will be incremented).

    Returns:
        Updated page data dict from Confluence API.
    """
    url = f"{base_url}/rest/api/content/{page_id}"
    payload = {
        "type": "page",
        "title": title,
        "version": {"number": current_version + 1},
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }

    resp = client.put(url, json=payload)
    resp.raise_for_status()
    return resp.json()


def create_blank_page(
    parent_page_url: str,
    page_title: str,
) -> str:
    """Create a blank placeholder page on Confluence.

    Intended to be called during ``tsu init`` so that the page_id is
    persisted in config *before* any CI/CD push happens.  This prevents
    Jenkins (or similar) from creating a new page on every run.

    Args:
        parent_page_url: Full Confluence URL of the parent page.
        page_title: Title for the new blank page.

    Returns:
        The new page ID string.

    Raises:
        NoCredentialsError: If no Confluence credentials are available.
        Exception: On any Confluence API / network error.
    """
    token = auth.get_token(prompt_if_missing=False)
    if not token:
        raise NoCredentialsError(
            "No Confluence credentials found (set via tsu auth set or env vars)"
        )

    base_url = extract_base_url(parent_page_url)
    headers = _build_headers(token)

    # Resolve parent page ID from URL
    _, parent_page_id = resolve_page_id(parent_page_url, bearer_token=token)

    # Resolve space key
    space_key = extract_space_key_from_url(parent_page_url) or ""
    if not space_key:
        space_key = get_space_key_from_page(
            base_url, parent_page_id, bearer_token=token,
        )

    placeholder_body = "<p>This page will be populated by tsu-cli.</p>"

    with httpx.Client(headers=headers, timeout=30.0) as client:
        result = _create_page(
            client,
            base_url,
            space_key,
            page_title,
            placeholder_body,
            parent_page_id,
        )

    return str(result["id"])


def fetch_page_html(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> str | None:
    """Pull the existing Confluence page body as HTML.

    Returns the raw Confluence storage-format HTML, or None if the page
    cannot be fetched (no page_id, no credentials, network error, etc.).
    """
    project_dir = project_dir or Path.cwd()
    confluence_config = config.read_confluence(project_dir, profile)
    page_id = confluence_config.get("page_id")
    if not page_id:
        raise NoPageIDError("No page_id in confluence.json")

    parent_page_url = confluence_config.get("parent_page_url", "")
    if not parent_page_url:
        raise NoParentPageError("No parent_page_url in confluence.json")

    token = auth.get_token(prompt_if_missing=False)
    if not token:
        raise NoCredentialsError("No Confluence credentials found (set via tsu auth set or env vars)")

    base_url = extract_base_url(parent_page_url)
    headers = _build_headers(token)

    try:
        with httpx.Client(headers=headers, timeout=15.0) as client:
            url = f"{base_url}/rest/api/content/{page_id}"
            resp = client.get(url, params={"expand": "body.storage,version"})
            if resp.status_code == 404:
                console.print(f"[red]  ↳ Page {page_id} not found (404)[/red]")
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("body", {}).get("storage", {}).get("value")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]  ↳ Fetch failed: {exc}[/red]")
        return None


def push(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> str:
    """Push the generated document to Confluence.

    Creates a new page or updates an existing one based on the page_id
    stored in the profile's confluence config.

    Args:
        project_dir: Project root directory (defaults to cwd).
        profile: Document profile name.

    Returns:
        The URL of the created/updated Confluence page.
    """
    project_dir = project_dir or Path.cwd()

    # Read configs
    confluence_config = config.read_confluence(project_dir, profile)
    parent_page_url = confluence_config.get("parent_page_url", "")
    page_title = confluence_config.get("page_title", "")
    page_id = confluence_config.get("page_id")

    # Validate required fields
    if not parent_page_url:
        console.print("[red]Error:[/red] parent_page_url not set. Run 'tsu init' first.")
        raise SystemExit(1)
    if not page_title:
        console.print("[red]Error:[/red] page_title not set. Run 'tsu init' first.")
        raise SystemExit(1)

    # Derive confluence_url from parent_page_url
    confluence_url = extract_base_url(parent_page_url)

    # Read generated document
    doc_path = config.get_document_path(project_dir, profile)
    if not doc_path.exists():
        console.print(
            f"[red]Error:[/red] {doc_path} not found. Run 'tsu generate' first."
        )
        raise SystemExit(1)

    doc_content = doc_path.read_text(encoding="utf-8")

    # Convert to Confluence storage format
    body_html = _markdown_to_confluence(doc_content)

    # Resolve credentials
    user = auth.get_user()
    token = auth.get_token()
    if not user or not token:
        console.print("[red]Error:[/red] Confluence credentials not configured.")
        console.print("Run 'tsu auth set' to configure credentials.")
        raise SystemExit(1)

    # Build auth headers — Bearer token, matching the working publish code pattern
    headers = _build_headers(token)

    # Resolve parent page ID from URL
    try:
        _, parent_page_id = resolve_page_id(parent_page_url, bearer_token=token)
        console.print(f"[dim]Resolved parent page ID {parent_page_id} from URL[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] Could not resolve parent page URL: {e}")
        raise SystemExit(1)

    # Resolve space key from URL (no API call needed)
    space_key = extract_space_key_from_url(parent_page_url) or ""
    if space_key:
        console.print(f"[dim]Resolved space key '{space_key}' from URL[/dim]")
    else:
        # Fall back to API call
        try:
            space_key = get_space_key_from_page(
                confluence_url, parent_page_id, bearer_token=token,
            )
            console.print(f"[dim]Resolved space key '{space_key}' from parent page[/dim]")
        except Exception as e:
            console.print(f"[red]Error:[/red] Could not resolve space key: {e}")
            raise SystemExit(1)

    # Make API calls — plain httpx.Client with Bearer token in headers
    # (matches the working code: no httpx.BasicAuth, auth via headers)
    with httpx.Client(
        headers=headers,
        timeout=30.0,
    ) as client:
        try:
            if page_id:
                # Try to update existing page
                page_data = _get_page(client, confluence_url, page_id)

                if page_data is None:
                    # Page was deleted — re-create
                    console.print(
                        f"[yellow]Warning:[/yellow] Page {page_id} not found. Creating new page."
                    )
                    result = _create_page(
                        client, confluence_url, space_key, page_title, body_html,
                        parent_page_id,
                    )
                else:
                    # Update existing page
                    current_version = page_data["version"]["number"]
                    result = _update_page(
                        client, confluence_url, page_id, page_title, body_html,
                        current_version,
                    )
                    console.print(
                        f"[green]✓[/green] Page updated (v{current_version} → v{current_version + 1})"
                    )
            else:
                # Create new page
                if not parent_page_id:
                    console.print(
                        "[yellow]Warning:[/yellow] No parent_page_id set. "
                        "Page will be created at the space root."
                    )
                result = _create_page(
                    client, confluence_url, space_key, page_title, body_html,
                    parent_page_id,
                )
                console.print("[green]✓[/green] Page created")

        except httpx.HTTPStatusError as e:
            _handle_http_error(e)
            raise SystemExit(1)

    # Extract page URL and ID from response
    new_page_id = str(result["id"])
    page_url = f"{confluence_url}{result.get('_links', {}).get('webui', '')}"

    # Persist page_id back to config for future updates
    if new_page_id != page_id:
        confluence_config["page_id"] = new_page_id
        config.write_confluence(confluence_config, project_dir, profile)
        console.print(f"[dim]Updated .tsu/confluence.json with page_id: {new_page_id}[/dim]")

    console.print(f"\n[bold]Page URL:[/bold] {page_url}")
    return page_url


def _handle_http_error(error: httpx.HTTPStatusError) -> None:
    """Parse and display a Confluence API error response."""
    status = error.response.status_code
    try:
        body = error.response.json()
        message = body.get("message", str(error))
    except Exception:
        message = error.response.text or str(error)

    if status == 401:
        console.print("[red]Error 401:[/red] Authentication failed.")
        console.print("Check your Confluence credentials with 'tsu auth status'.")
    elif status == 403:
        console.print("[red]Error 403:[/red] Permission denied.")
        console.print(f"[dim]{message}[/dim]")
    elif status == 404:
        console.print("[red]Error 404:[/red] Resource not found.")
        console.print(f"[dim]{message}[/dim]")
    else:
        console.print(f"[red]Error {status}:[/red] {message}")
