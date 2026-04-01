"""Confluence authentication management for tsu-cli.

Token resolution priority:
  1. CONFLUENCE_TOKEN env var (for CI/scripts)
  2. System keychain via keyring (service=tsu-cli, username=confluence)
  3. Interactive prompt (offers to store in keychain)

User email resolution:
  1. CONFLUENCE_USER env var
  2. System keychain (service=tsu-cli, username=confluence-user)
  3. Interactive prompt
"""

from __future__ import annotations

import os

import keyring
import typer
from rich.console import Console

SERVICE_NAME = "tsu-cli"
TOKEN_USERNAME = "confluence"
USER_USERNAME = "confluence-user"

console = Console()


def get_token(prompt_if_missing: bool = True) -> str | None:
    """Resolve Confluence API token from env var, keyring, or interactive prompt.

    Args:
        prompt_if_missing: If True, prompt the user when no token is found.

    Returns:
        The API token string, or None if not found and prompt_if_missing is False.
    """
    # 1. Environment variable
    token = os.environ.get("CONFLUENCE_TOKEN")
    if token:
        return token

    # 2. System keychain
    token = keyring.get_password(SERVICE_NAME, TOKEN_USERNAME)
    if token:
        return token

    # 3. Interactive prompt
    if not prompt_if_missing:
        return None

    token = typer.prompt("Confluence API token", hide_input=True)
    if token and typer.confirm("Store token in system keychain?", default=True):
        keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, token)
        console.print("[green]✓[/green] Token stored in keychain")
    return token


def get_user(prompt_if_missing: bool = True) -> str | None:
    """Resolve Confluence user email from env var, keyring, or interactive prompt.

    Args:
        prompt_if_missing: If True, prompt the user when no email is found.

    Returns:
        The user email string, or None if not found and prompt_if_missing is False.
    """
    # 1. Environment variable
    user = os.environ.get("CONFLUENCE_USER")
    if user:
        return user

    # 2. System keychain
    user = keyring.get_password(SERVICE_NAME, USER_USERNAME)
    if user:
        return user

    # 3. Interactive prompt
    if not prompt_if_missing:
        return None

    user = typer.prompt("Confluence user email")
    if user and typer.confirm("Store email in system keychain?", default=True):
        keyring.set_password(SERVICE_NAME, USER_USERNAME, user)
        console.print("[green]✓[/green] Email stored in keychain")
    return user


def set_credentials(user: str, token: str) -> None:
    """Store both user email and token in the system keychain."""
    keyring.set_password(SERVICE_NAME, USER_USERNAME, user)
    keyring.set_password(SERVICE_NAME, TOKEN_USERNAME, token)


def clear_credentials() -> None:
    """Remove stored credentials from the system keychain."""
    try:
        keyring.delete_password(SERVICE_NAME, TOKEN_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
    try:
        keyring.delete_password(SERVICE_NAME, USER_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


def get_status() -> dict[str, str]:
    """Check where credentials are configured.

    Returns:
        Dict with 'token' and 'user' keys, values are 'env', 'keyring', or 'not set'.
    """
    # Token status
    if os.environ.get("CONFLUENCE_TOKEN"):
        token_status = "env"
    elif keyring.get_password(SERVICE_NAME, TOKEN_USERNAME):
        token_status = "keyring"
    else:
        token_status = "not set"

    # User status
    if os.environ.get("CONFLUENCE_USER"):
        user_status = "env"
    elif keyring.get_password(SERVICE_NAME, USER_USERNAME):
        user_status = "keyring"
    else:
        user_status = "not set"

    return {"token": token_status, "user": user_status}
