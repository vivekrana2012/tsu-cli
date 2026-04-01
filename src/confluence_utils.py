"""Confluence URL resolution utilities for tsu-cli.

Handles extracting page IDs and base URLs from various Confluence URL formats:
  - /pages/viewpage.action?pageId=12345
  - /wiki/spaces/SPACE/pages/12345/Page+Title
  - /wiki/display/SPACE/Page+Title
  - /wiki/x/shortcode (tiny links)
"""

from __future__ import annotations

import re
from typing import Tuple
from urllib.parse import parse_qs, unquote, urlparse

import httpx


def extract_base_url(url: str) -> str:
    """Extract the Confluence base URL (scheme + host + optional /wiki prefix).

    Examples:
        https://example.atlassian.net/wiki/spaces/ENG/pages/123  → https://example.atlassian.net/wiki
        https://confluence.example.com/display/ENG/Page           → https://confluence.example.com

    Returns:
        Base URL string without trailing slash.
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Atlassian Cloud URLs typically include /wiki
    path = parsed.path
    if path.startswith("/wiki"):
        base += "/wiki"

    return base.rstrip("/")


def extract_page_id_from_url(url: str) -> str | None:
    """Try to extract a numeric page ID directly from a Confluence URL.

    Supports:
        ?pageId=12345
        /pages/12345
        /pages/12345/Page+Title

    Returns:
        Page ID string, or None if not found.
    """
    parsed = urlparse(url)

    # Check query parameter: ?pageId=12345
    qs = parse_qs(parsed.query)
    page_ids = qs.get("pageId")
    if page_ids:
        return page_ids[0]

    # Check path pattern: /pages/<numeric_id>
    match = re.search(r"/pages/(\d+)", parsed.path)
    if match:
        return match.group(1)

    return None


def extract_space_and_title_from_url(url: str) -> Tuple[str | None, str | None]:
    """Extract space key and page title from a Confluence display URL.

    Supports:
        /display/SPACE/Page+Title
        /wiki/display/SPACE/Page+Title

    Returns:
        Tuple of (space_key, title), either may be None.
    """
    parsed = urlparse(url)
    path = parsed.path

    # /display/SPACE/Title or /wiki/display/SPACE/Title
    match = re.search(r"/display/([^/]+)/(.+?)/?$", path)
    if match:
        space_key = match.group(1)
        title = unquote(match.group(2).replace("+", " "))
        return (space_key, title)

    return (None, None)


def extract_space_key_from_url(url: str) -> str | None:
    """Extract space key from a Confluence URL path.

    Supports:
        /spaces/SPACE/pages/12345/Title
        /wiki/spaces/SPACE/pages/12345/Title
        /display/SPACE/Title
        /wiki/display/SPACE/Title

    Returns:
        Space key string, or None if not found.
    """
    parsed = urlparse(url)
    path = parsed.path

    # /spaces/SPACE/... (new Confluence DC / Cloud URL format)
    match = re.search(r"/spaces/([^/]+)", path)
    if match:
        return match.group(1)

    # /display/SPACE/...
    match = re.search(r"/display/([^/]+)", path)
    if match:
        return match.group(1)

    return None


def get_page_id_by_space_and_title(
    base_url: str,
    space_key: str,
    title: str,
    auth: httpx.BasicAuth | None = None,
    bearer_token: str | None = None,
) -> str:
    """Look up a page ID by space key and title via the Confluence REST API.

    Args:
        base_url: Confluence base URL.
        space_key: Space key (e.g. 'ENG').
        title: Exact page title.
        auth: httpx BasicAuth credentials (for Confluence Cloud).
        bearer_token: Bearer token (for Confluence Server/Data Center).

    Returns:
        Page ID string.

    Raises:
        Exception: If the page cannot be found.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    with httpx.Client(auth=auth, headers=headers, timeout=30.0) as client:
        resp = client.get(
            f"{base_url}/rest/api/content",
            params={"spaceKey": space_key, "title": title},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

    if not results:
        raise Exception(
            f"No page found with title '{title}' in space '{space_key}'"
        )

    return str(results[0]["id"])


def resolve_page_id(
    url: str,
    auth: httpx.BasicAuth | None = None,
    bearer_token: str | None = None,
) -> Tuple[str, str]:
    """Resolve page ID from any supported Confluence URL format.

    Tries multiple methods in order:
      1. Extract page ID directly from URL
      2. Extract space/title and search for page ID via REST API

    Args:
        url: Confluence page URL (any supported format).
        auth: httpx BasicAuth credentials (for Confluence Cloud).
        bearer_token: Bearer token (for Confluence Server/Data Center).

    Returns:
        Tuple of (base_url, page_id).

    Raises:
        Exception: If page ID cannot be resolved.
    """
    base_url = extract_base_url(url)

    # 1. Try to extract page ID directly from URL
    page_id = extract_page_id_from_url(url)
    if page_id:
        return (base_url, page_id)

    # 2. Try to get page ID from space and title
    space_key, title = extract_space_and_title_from_url(url)
    if space_key and title:
        page_id = get_page_id_by_space_and_title(
            base_url, space_key, title,
            auth=auth, bearer_token=bearer_token,
        )
        return (base_url, page_id)

    raise Exception(f"Could not resolve page ID from URL: {url}")


def get_space_key_from_page(
    base_url: str,
    page_id: str,
    auth: httpx.BasicAuth | None = None,
    bearer_token: str | None = None,
) -> str:
    """Fetch the space key for a given page ID from the Confluence REST API.

    Consistent with the pattern used in the working publish code — retrieves
    parent page details and extracts the space key from the ``space`` field.

    Args:
        base_url: Confluence base URL.
        page_id: Confluence page ID.
        auth: httpx BasicAuth credentials.
        bearer_token: Bearer token for auth.

    Returns:
        The space key string.

    Raises:
        Exception: If the space key cannot be determined.
    """
    headers: dict[str, str] = {"Accept": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    with httpx.Client(auth=auth, headers=headers, timeout=30.0) as client:
        resp = client.get(f"{base_url}/rest/api/content/{page_id}")
        if resp.status_code != 200:
            raise Exception(
                f"Failed to fetch page {page_id}: {resp.status_code} - {resp.text}"
            )
        data = resp.json()

    space_key = data.get("space", {}).get("key")
    if not space_key:
        raise Exception(
            f"Could not determine space key from page {page_id}"
        )

    return space_key
