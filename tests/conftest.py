"""Shared fixtures for tsu-cli tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_runner() -> CliRunner:
    """Return a Typer CliRunner for invoking CLI commands."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Temporary project directory with .tsu/ scaffold
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with an initialized .tsu/ folder.

    Layout:
        tmp_path/
        ├── .tsu/
        │   ├── config.json
        │   ├── confluence.json          (tech profile)
        │   └── generate.md              (tech profile prompt)
        └── (empty project root)

    Returns the project root path.
    """
    tsu_dir = tmp_path / ".tsu"
    tsu_dir.mkdir()

    # config.json
    (tsu_dir / "config.json").write_text(
        json.dumps({"model": "gpt-4o"}, indent=2) + "\n",
        encoding="utf-8",
    )

    # confluence.json (tech profile — legacy filename)
    (tsu_dir / "confluence.json").write_text(
        json.dumps(
            {
                "parent_page_url": "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent",
                "page_title": "TestProject - Tech Overview",
                "page_id": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # generate.md (tech profile prompt)
    (tsu_dir / "generate.md").write_text(
        "# Tech Prompt\nAnalyze the project.\n"
        "{{ additional_instructions }}\n"
        "{{ existing_document }}\n",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def tmp_project_with_profiles(tmp_project: Path) -> Path:
    """Extend tmp_project with an additional 'ops' profile.

    Adds:
        .tsu/generate-ops.md
        .tsu/confluence-ops.json
    """
    tsu_dir = tmp_project / ".tsu"

    (tsu_dir / "generate-ops.md").write_text(
        "# Ops Prompt\nDescribe operations.\n",
        encoding="utf-8",
    )

    (tsu_dir / "confluence-ops.json").write_text(
        json.dumps(
            {
                "parent_page_url": "https://example.atlassian.net/wiki/spaces/OPS/pages/222/Parent",
                "page_title": "TestProject - Ops",
                "page_id": None,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return tmp_project


# ---------------------------------------------------------------------------
# Keyring mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_keyring():
    """Patch keyring get/set/delete so no real keychain access occurs.

    The fixture returns a dict acting as an in-memory keyring store.
    """
    store: dict[tuple[str, str], str] = {}

    def _get(service: str, username: str) -> str | None:
        return store.get((service, username))

    def _set(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    def _delete(service: str, username: str) -> None:
        key = (service, username)
        if key not in store:
            import keyring.errors
            raise keyring.errors.PasswordDeleteError("not found")
        del store[key]

    with (
        patch("keyring.get_password", side_effect=_get),
        patch("keyring.set_password", side_effect=_set),
        patch("keyring.delete_password", side_effect=_delete),
    ):
        yield store


# ---------------------------------------------------------------------------
# httpx mock helpers
# ---------------------------------------------------------------------------


def make_mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
) -> MagicMock:
    """Create a mock httpx.Response with the given status/body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        import httpx

        request = MagicMock()
        request.url = "https://mock"
        resp.request = request
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=request, response=resp,
        )
    return resp
