"""Tests for tsu_cli.auth — credential resolution chain."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tsu_cli.auth import (
    SERVICE_NAME,
    TOKEN_USERNAME,
    USER_USERNAME,
    clear_credentials,
    get_status,
    get_token,
    get_user,
    set_credentials,
)


# ===================================================================
# get_token
# ===================================================================


class TestGetToken:
    """Tests #32-34: get_token resolution chain."""

    def test_env_var(self, mock_keyring):
        """#32 CONFLUENCE_TOKEN env var → returns env value."""
        with patch.dict(os.environ, {"CONFLUENCE_TOKEN": "env-token"}):
            assert get_token(prompt_if_missing=False) == "env-token"

    def test_keyring(self, mock_keyring):
        """#33 No env var, keyring has value → returns keyring value."""
        mock_keyring[(SERVICE_NAME, TOKEN_USERNAME)] = "kr-token"
        with patch.dict(os.environ, {}, clear=True):
            # Ensure CONFLUENCE_TOKEN is not set
            os.environ.pop("CONFLUENCE_TOKEN", None)
            assert get_token(prompt_if_missing=False) == "kr-token"

    def test_missing_no_prompt(self, mock_keyring):
        """#34 Both absent + prompt_if_missing=False → None."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_TOKEN", None)
            assert get_token(prompt_if_missing=False) is None


# ===================================================================
# get_user
# ===================================================================


class TestGetUser:
    """Tests #35-37: get_user resolution chain."""

    def test_env_var(self, mock_keyring):
        """#35 CONFLUENCE_USER env var → returns env value."""
        with patch.dict(os.environ, {"CONFLUENCE_USER": "user@example.com"}):
            assert get_user(prompt_if_missing=False) == "user@example.com"

    def test_keyring(self, mock_keyring):
        """#36 No env var, keyring has value → returns keyring value."""
        mock_keyring[(SERVICE_NAME, USER_USERNAME)] = "kr-user@example.com"
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_USER", None)
            assert get_user(prompt_if_missing=False) == "kr-user@example.com"

    def test_missing_no_prompt(self, mock_keyring):
        """#37 Both absent + prompt_if_missing=False → None."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_USER", None)
            assert get_user(prompt_if_missing=False) is None


# ===================================================================
# set_credentials / clear_credentials
# ===================================================================


class TestSetCredentials:
    """Tests #38: set_credentials."""

    def test_stores_both(self, mock_keyring):
        """#38 set_credentials calls keyring.set_password correctly."""
        set_credentials("user@example.com", "my-token")
        assert mock_keyring[(SERVICE_NAME, USER_USERNAME)] == "user@example.com"
        assert mock_keyring[(SERVICE_NAME, TOKEN_USERNAME)] == "my-token"


class TestClearCredentials:
    """Tests #39-40: clear_credentials."""

    def test_clears(self, mock_keyring):
        """#39 clear_credentials removes stored credentials."""
        mock_keyring[(SERVICE_NAME, TOKEN_USERNAME)] = "tok"
        mock_keyring[(SERVICE_NAME, USER_USERNAME)] = "usr"
        clear_credentials()
        assert (SERVICE_NAME, TOKEN_USERNAME) not in mock_keyring
        assert (SERVICE_NAME, USER_USERNAME) not in mock_keyring

    def test_handles_not_found(self, mock_keyring):
        """#40 clear_credentials handles PasswordDeleteError gracefully."""
        # Nothing stored — should not raise
        clear_credentials()


# ===================================================================
# get_status
# ===================================================================


class TestGetStatus:
    """Tests #41-43: get_status."""

    def test_env(self, mock_keyring):
        """#41 Token in env → 'env'."""
        with patch.dict(os.environ, {"CONFLUENCE_TOKEN": "t", "CONFLUENCE_USER": "u"}):
            status = get_status()
        assert status["token"] == "env"
        assert status["user"] == "env"

    def test_keyring_source(self, mock_keyring):
        """#42 Token in keyring → 'keyring'."""
        mock_keyring[(SERVICE_NAME, TOKEN_USERNAME)] = "tok"
        mock_keyring[(SERVICE_NAME, USER_USERNAME)] = "usr"
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_TOKEN", None)
            os.environ.pop("CONFLUENCE_USER", None)
            status = get_status()
        assert status["token"] == "keyring"
        assert status["user"] == "keyring"

    def test_not_set(self, mock_keyring):
        """#43 Nothing set → 'not set'."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_TOKEN", None)
            os.environ.pop("CONFLUENCE_USER", None)
            status = get_status()
        assert status["token"] == "not set"
        assert status["user"] == "not set"


# ===================================================================
# Interactive prompt paths
# ===================================================================


class TestGetTokenPrompt:
    """Tests for get_token interactive prompt path (lines 52-56)."""

    def test_prompt_stores_in_keychain(self, mock_keyring):
        """prompt_if_missing=True, user enters token and confirms store."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_TOKEN", None)
            with (
                patch("tsu_cli.auth.typer.prompt", return_value="prompted-token"),
                patch("tsu_cli.auth.typer.confirm", return_value=True),
                patch("tsu_cli.auth.console"),
            ):
                result = get_token(prompt_if_missing=True)
        assert result == "prompted-token"
        assert mock_keyring[(SERVICE_NAME, TOKEN_USERNAME)] == "prompted-token"

    def test_prompt_declines_store(self, mock_keyring):
        """prompt_if_missing=True, user enters token but declines keychain."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_TOKEN", None)
            with (
                patch("tsu_cli.auth.typer.prompt", return_value="tmp-token"),
                patch("tsu_cli.auth.typer.confirm", return_value=False),
            ):
                result = get_token(prompt_if_missing=True)
        assert result == "tmp-token"
        assert (SERVICE_NAME, TOKEN_USERNAME) not in mock_keyring


class TestGetUserPrompt:
    """Tests for get_user interactive prompt path (lines 82-86)."""

    def test_prompt_stores_in_keychain(self, mock_keyring):
        """prompt_if_missing=True, user enters email and confirms store."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_USER", None)
            with (
                patch("tsu_cli.auth.typer.prompt", return_value="me@example.com"),
                patch("tsu_cli.auth.typer.confirm", return_value=True),
                patch("tsu_cli.auth.console"),
            ):
                result = get_user(prompt_if_missing=True)
        assert result == "me@example.com"
        assert mock_keyring[(SERVICE_NAME, USER_USERNAME)] == "me@example.com"

    def test_prompt_declines_store(self, mock_keyring):
        """prompt_if_missing=True, user enters email but declines keychain."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CONFLUENCE_USER", None)
            with (
                patch("tsu_cli.auth.typer.prompt", return_value="me@example.com"),
                patch("tsu_cli.auth.typer.confirm", return_value=False),
            ):
                result = get_user(prompt_if_missing=True)
        assert result == "me@example.com"
        assert (SERVICE_NAME, USER_USERNAME) not in mock_keyring
