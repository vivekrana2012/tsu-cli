"""Tests for tsu_cli.publisher — markdown conversion, headers, and API calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tsu_cli.publisher import (
    NoCredentialsError,
    NoPageIDError,
    NoParentPageError,
    _build_headers,
    _create_page,
    _get_page,
    _markdown_to_confluence,
    _update_page,
    create_blank_page,
    fetch_page_html,
    push,
)


# ===================================================================
# Unit tests — pure helpers
# ===================================================================


class TestMarkdownToConfluence:
    """Tests #44-45: _markdown_to_confluence."""

    def test_headings(self):
        """#44 Markdown heading → HTML heading."""
        result = _markdown_to_confluence("# Hello")
        assert result.startswith("<h1")
        assert "Hello</h1>" in result

    def test_fenced_code(self):
        """#45 Fenced code block → <pre><code>."""
        md_text = "```python\nprint('hi')\n```"
        result = _markdown_to_confluence(md_text)
        assert "<code" in result
        assert "print" in result


class TestBuildHeaders:
    """Test #46: _build_headers."""

    def test_headers(self):
        """#46 Returns Authorization, Content-Type, Accept."""
        h = _build_headers("my-token")
        assert h["Authorization"] == "Bearer my-token"
        assert h["Content-Type"] == "application/json"
        assert h["Accept"] == "application/json"


# ===================================================================
# Integration tests — mocked httpx client
# ===================================================================


def _mock_client():
    """Create a mock httpx.Client context manager."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


class TestGetPage:
    """Tests #57-58: _get_page."""

    def test_found(self):
        """#57 GET 200 → returns page data."""
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "123", "version": {"number": 3}}
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        result = _get_page(client, "https://x.atlassian.net/wiki", "123")
        assert result is not None
        assert result["id"] == "123"

    def test_not_found(self):
        """#58 GET 404 → returns None."""
        client = MagicMock()
        resp = MagicMock()
        resp.status_code = 404
        client.get.return_value = resp

        result = _get_page(client, "https://x.atlassian.net/wiki", "999")
        assert result is None


class TestCreatePage:
    """Test #59: _create_page."""

    def test_payload(self):
        """#59 POST payload has space, title, body, ancestors."""
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"id": "new1"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        _create_page(
            client, "https://x.atlassian.net/wiki",
            "ENG", "My Doc", "<p>body</p>", "parent1",
        )

        call_kwargs = client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["space"]["key"] == "ENG"
        assert payload["title"] == "My Doc"
        assert payload["body"]["storage"]["value"] == "<p>body</p>"
        assert payload["ancestors"] == [{"id": "parent1"}]


class TestUpdatePage:
    """Test #60: _update_page."""

    def test_version_increment(self):
        """#60 PUT payload version incremented by 1."""
        client = MagicMock()
        resp = MagicMock()
        resp.json.return_value = {"id": "123"}
        resp.raise_for_status = MagicMock()
        client.put.return_value = resp

        _update_page(
            client, "https://x.atlassian.net/wiki",
            "123", "Title", "<p>new</p>", 5,
        )

        call_kwargs = client.put.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["version"]["number"] == 6


class TestPush:
    """Tests #61-65, #69: push flow."""

    def _setup_push(self, tmp_project: Path, profile: str = "tech", page_id=None):
        """Helper to prepare tmp_project for push tests."""
        tsu_dir = tmp_project / ".tsu"
        from tsu_cli.config import _confluence_filename, _document_filename

        # Write confluence config
        conf_data = {
            "parent_page_url": "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent",
            "page_title": "Test Doc",
            "page_id": page_id,
        }
        (tsu_dir / _confluence_filename(profile)).write_text(
            json.dumps(conf_data, indent=2) + "\n", encoding="utf-8",
        )

        # Write document
        (tsu_dir / _document_filename(profile)).write_text(
            "# Test\nSome content\n", encoding="utf-8",
        )

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_create_new(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """#61 No page_id → creates page, persists page_id."""
        self._setup_push(tmp_project, page_id=None)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        resp = MagicMock()
        resp.json.return_value = {"id": "new42", "_links": {"webui": "/pages/new42"}}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        push(tmp_project, "tech")

        # page_id persisted
        conf = json.loads((tmp_project / ".tsu" / "confluence.json").read_text())
        assert conf["page_id"] == "new42"

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_update_existing(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """#62 Has page_id → updates page."""
        self._setup_push(tmp_project, page_id="existing99")
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        # _get_page returns existing page
        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"id": "existing99", "version": {"number": 3}}
        get_resp.raise_for_status = MagicMock()

        # _update_page response
        put_resp = MagicMock()
        put_resp.json.return_value = {"id": "existing99", "_links": {"webui": "/pages/existing99"}}
        put_resp.raise_for_status = MagicMock()

        client.get.return_value = get_resp
        client.put.return_value = put_resp

        push(tmp_project, "tech")
        client.put.assert_called_once()

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_page_deleted_recreate(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """#63 page_id exists but 404 → re-creates page."""
        self._setup_push(tmp_project, page_id="gone404")
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        # _get_page returns 404
        get_resp = MagicMock()
        get_resp.status_code = 404
        client.get.return_value = get_resp

        # _create_page response
        post_resp = MagicMock()
        post_resp.json.return_value = {"id": "recreated1", "_links": {"webui": "/pages/recreated1"}}
        post_resp.raise_for_status = MagicMock()
        client.post.return_value = post_resp

        push(tmp_project, "tech")
        client.post.assert_called_once()

    @patch("tsu_cli.publisher.auth")
    def test_no_credentials(self, mock_auth, tmp_project: Path):
        """#64 No creds → SystemExit(1)."""
        self._setup_push(tmp_project)
        mock_auth.get_user.return_value = None
        mock_auth.get_token.return_value = None

        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    def test_no_parent_url(self, tmp_project: Path):
        """#65 Empty parent_page_url → SystemExit(1)."""
        tsu_dir = tmp_project / ".tsu"
        conf_data = {"parent_page_url": "", "page_title": "T", "page_id": None}
        (tsu_dir / "confluence.json").write_text(
            json.dumps(conf_data, indent=2) + "\n", encoding="utf-8",
        )
        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="OPS")
    def test_push_ops_profile_uses_correct_files(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """#69 Profile 'ops' reads confluence-ops.json, writes page_id back to it."""
        self._setup_push(tmp_project, profile="ops", page_id=None)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        resp = MagicMock()
        resp.json.return_value = {"id": "ops42", "_links": {"webui": "/pages/ops42"}}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        push(tmp_project, "ops")

        # Verify ops config was updated
        ops_conf = json.loads((tmp_project / ".tsu" / "confluence-ops.json").read_text())
        assert ops_conf["page_id"] == "ops42"

        # Tech config unchanged
        tech_conf = json.loads((tmp_project / ".tsu" / "confluence.json").read_text())
        assert tech_conf["page_id"] is None


# ===================================================================
# fetch_page_html
# ===================================================================


class TestFetchPageHtml:
    """Tests #66-67: fetch_page_html."""

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    def test_returns_html(self, MockClient, mock_auth, tmp_project: Path):
        """#66 Mock API → returns HTML body."""
        # Set page_id in confluence config
        tsu_dir = tmp_project / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "456"
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "body": {"storage": {"value": "<p>Hello</p>"}},
            "version": {"number": 1},
        }
        resp.raise_for_status = MagicMock()
        client.get.return_value = resp

        result = fetch_page_html(tmp_project)
        assert result == "<p>Hello</p>"

    def test_no_page_id(self, tmp_project: Path):
        """#67 No page_id → raises NoPageIDError."""
        with pytest.raises(NoPageIDError):
            fetch_page_html(tmp_project)


# ===================================================================
# create_blank_page
# ===================================================================


class TestCreateBlankPage:
    """Test #68: create_blank_page."""

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_returns_page_id(self, mock_space, mock_resolve, MockClient, mock_auth):
        """#68 Mock resolve + create → returns new page ID."""
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        resp = MagicMock()
        resp.json.return_value = {"id": "blank1"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        result = create_blank_page(
            "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent",
            "New Blank Page",
        )
        assert result == "blank1"
