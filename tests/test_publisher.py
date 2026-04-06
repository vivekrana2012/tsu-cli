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
    html_to_markdown,
    pull,
    pull_by_url,
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


# ===================================================================
# Additional coverage tests
# ===================================================================


class TestCreateBlankPageNoCredentials:
    """Test create_blank_page with no credentials."""

    @patch("tsu_cli.publisher.auth")
    def test_no_token_raises(self, mock_auth):
        """No token → NoCredentialsError."""
        mock_auth.get_token.return_value = None
        with pytest.raises(NoCredentialsError):
            create_blank_page(
                "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent",
                "Title",
            )


class TestCreateBlankPageSpaceKeyFallback:
    """Test create_blank_page space key fallback to API."""

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value=None)
    @patch("tsu_cli.publisher.get_space_key_from_page", return_value="FALLBACK")
    def test_fallback_to_api(self, mock_space_api, mock_space_url, mock_resolve, MockClient, mock_auth):
        """No space key from URL → falls back to get_space_key_from_page."""
        mock_auth.get_token.return_value = "tok"
        client = _mock_client()
        MockClient.return_value = client
        resp = MagicMock()
        resp.json.return_value = {"id": "new1"}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        result = create_blank_page(
            "https://example.atlassian.net/wiki/pages/viewpage.action?pageId=111",
            "Title",
        )
        assert result == "new1"
        mock_space_api.assert_called_once()


class TestFetchPageHtmlNoParentUrl:
    """Test fetch_page_html when parent_page_url is missing."""

    def test_no_parent_url(self, tmp_project: Path):
        """No parent_page_url → raises NoParentPageError."""
        tsu_dir = tmp_project / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "123"
        conf["parent_page_url"] = ""
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        with pytest.raises(NoParentPageError):
            fetch_page_html(tmp_project)


class TestFetchPageHtmlNoCredentials:
    """Test fetch_page_html when credentials are missing."""

    @patch("tsu_cli.publisher.auth")
    def test_no_token(self, mock_auth, tmp_project: Path):
        """No token → raises NoCredentialsError."""
        tsu_dir = tmp_project / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "123"
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        mock_auth.get_token.return_value = None
        with pytest.raises(NoCredentialsError):
            fetch_page_html(tmp_project)


class TestFetchPageHtml404:
    """Test fetch_page_html when page returns 404."""

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    def test_page_404_returns_none(self, MockClient, mock_auth, tmp_project: Path):
        """Page 404 → returns None."""
        tsu_dir = tmp_project / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "gone"
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        mock_auth.get_token.return_value = "tok"
        client = _mock_client()
        MockClient.return_value = client
        resp = MagicMock()
        resp.status_code = 404
        client.get.return_value = resp

        result = fetch_page_html(tmp_project)
        assert result is None


class TestFetchPageHtmlException:
    """Test fetch_page_html when an exception occurs."""

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    def test_network_error_returns_none(self, MockClient, mock_auth, tmp_project: Path):
        """Network error → returns None."""
        tsu_dir = tmp_project / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "123"
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        mock_auth.get_token.return_value = "tok"
        client = _mock_client()
        MockClient.return_value = client
        client.get.side_effect = httpx.ConnectError("Connection refused")

        result = fetch_page_html(tmp_project)
        assert result is None


class TestPushNoPageTitle:
    """Test push when page_title is empty."""

    def test_no_page_title(self, tmp_project: Path):
        """Empty page_title → SystemExit(1)."""
        tsu_dir = tmp_project / ".tsu"
        conf = {"parent_page_url": "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent", "page_title": "", "page_id": None}
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")
        with pytest.raises(SystemExit):
            push(tmp_project, "tech")


class TestPushNoDocument:
    """Test push when document file doesn't exist."""

    def test_no_document(self, tmp_project: Path):
        """Missing document.md → SystemExit(1)."""
        # Ensure document.md does not exist (it shouldn't by default)
        doc_path = tmp_project / ".tsu" / "document.md"
        if doc_path.exists():
            doc_path.unlink()
        with pytest.raises(SystemExit):
            push(tmp_project, "tech")


class TestPushResolveErrors:
    """Test push when resolve_page_id or space key resolution fails."""

    def _setup_for_push(self, tmp_project: Path):
        tsu_dir = tmp_project / ".tsu"
        from tsu_cli.config import _confluence_filename, _document_filename
        (tsu_dir / _document_filename("tech")).write_text("# Doc\nContent\n")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.resolve_page_id", side_effect=Exception("Cannot resolve"))
    def test_resolve_page_id_error(self, mock_resolve, mock_auth, tmp_project: Path):
        """resolve_page_id fails → SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"
        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value=None)
    @patch("tsu_cli.publisher.get_space_key_from_page", side_effect=Exception("No space"))
    def test_space_key_fallback_error(self, mock_space_api, mock_space_url, mock_resolve, mock_auth, tmp_project: Path):
        """Space key fallback fails → SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"
        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value=None)
    @patch("tsu_cli.publisher.get_space_key_from_page", return_value="ENG")
    @patch("tsu_cli.publisher.httpx.Client")
    def test_space_key_fallback_success(self, MockClient, mock_space_api, mock_space_url, mock_resolve, mock_auth, tmp_project: Path):
        """Space key fallback succeeds → page created."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client
        resp = MagicMock()
        resp.json.return_value = {"id": "new1", "_links": {"webui": "/pages/new1"}}
        resp.raise_for_status = MagicMock()
        client.post.return_value = resp

        push(tmp_project, "tech")
        mock_space_api.assert_called_once()


class TestPushHttpError:
    """Test push when Confluence API returns an HTTP error."""

    def _setup_for_push(self, tmp_project: Path):
        tsu_dir = tmp_project / ".tsu"
        from tsu_cli.config import _document_filename
        (tsu_dir / _document_filename("tech")).write_text("# Doc\nContent\n")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_http_401(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """HTTP 401 → _handle_http_error called, SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Unauthorized"}
        mock_response.text = "Unauthorized"
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)
        client.post.side_effect = error

        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_http_403(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """HTTP 403 → _handle_http_error, SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Forbidden"}
        mock_response.text = "Forbidden"
        error = httpx.HTTPStatusError("403", request=MagicMock(), response=mock_response)
        client.post.side_effect = error

        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_http_500(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """HTTP 500 → _handle_http_error generic branch, SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Server Error"}
        mock_response.text = "Server Error"
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)
        client.post.side_effect = error

        with pytest.raises(SystemExit):
            push(tmp_project, "tech")

    @patch("tsu_cli.publisher.auth")
    @patch("tsu_cli.publisher.httpx.Client")
    @patch("tsu_cli.publisher.resolve_page_id", return_value=("https://example.atlassian.net/wiki", "111"))
    @patch("tsu_cli.publisher.extract_space_key_from_url", return_value="ENG")
    def test_http_404_error(self, mock_space, mock_resolve, MockClient, mock_auth, tmp_project: Path):
        """HTTP 404 from API → _handle_http_error 404 branch, SystemExit(1)."""
        self._setup_for_push(tmp_project)
        mock_auth.get_user.return_value = "u@example.com"
        mock_auth.get_token.return_value = "tok"

        client = _mock_client()
        MockClient.return_value = client

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_response.text = "Not Found"
        error = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        client.post.side_effect = error

        with pytest.raises(SystemExit):
            push(tmp_project, "tech")


class TestHandleHttpErrorNonJsonBody:
    """Test _handle_http_error when response body is not JSON."""

    def test_non_json_body(self):
        """Non-JSON response → falls back to response.text."""
        from tsu_cli.publisher import _handle_http_error

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "Bad Gateway"
        error = httpx.HTTPStatusError("502", request=MagicMock(), response=mock_response)
        _handle_http_error(error)


# ===================================================================
# html_to_markdown
# ===================================================================


class TestHtmlToMarkdown:
    """Tests #91-94: html_to_markdown conversion."""

    def test_basic_paragraph(self):
        """#91 Basic HTML → markdown."""
        assert html_to_markdown("<p>Hello world</p>") == "Hello world"

    def test_headings(self):
        result = html_to_markdown("<h1>Title</h1><h2>Sub</h2>")
        assert "# Title" in result
        assert "## Sub" in result

    def test_table(self):
        """#92 HTML table → markdown table."""
        html = (
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td>1</td><td>2</td></tr></table>"
        )
        result = html_to_markdown(html)
        assert "A" in result
        assert "1" in result

    def test_code_block(self):
        """#93 <pre><code> → fenced code block."""
        html = "<pre><code>print('hi')</code></pre>"
        result = html_to_markdown(html)
        assert "print" in result

    def test_empty_string(self):
        """#94 Empty input → empty string."""
        assert html_to_markdown("") == ""

    def test_none_like_empty(self):
        assert html_to_markdown("") == ""

    def test_strips_images(self):
        html = "<p>Text <img src='logo.png'/> more</p>"
        result = html_to_markdown(html)
        assert "logo.png" not in result
        assert "Text" in result


# ===================================================================
# pull
# ===================================================================


class TestPull:
    """Tests #95-98: pull() — fetch, convert, write."""

    @patch("tsu_cli.publisher.fetch_page_html", return_value="<p>Remote content</p>")
    def test_writes_document(self, mock_fetch, tmp_path: Path):
        """#95 Mock API → .tsu/document.md written with converted markdown."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        doc_path = pull(tmp_path, "tech")
        assert doc_path.exists()
        content = doc_path.read_text()
        assert "Remote content" in content

    @patch("tsu_cli.publisher.fetch_page_html", side_effect=NoPageIDError("no id"))
    def test_no_page_id_propagates(self, mock_fetch, tmp_path: Path):
        """#96 No page_id → raises NoPageIDError."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        with pytest.raises(NoPageIDError):
            pull(tmp_path, "tech")

    @patch("tsu_cli.publisher.fetch_page_html", return_value="<p>Ops stuff</p>")
    def test_profile_filename(self, mock_fetch, tmp_path: Path):
        """#97 tsu pull --profile ops → writes .tsu/document-ops.md."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        doc_path = pull(tmp_path, "ops")
        assert doc_path.name == "document-ops.md"
        assert "Ops stuff" in doc_path.read_text()

    @patch("tsu_cli.publisher.fetch_page_html", return_value="<p>Updated content</p>")
    def test_overwrites_existing(self, mock_fetch, tmp_path: Path):
        """#98 Existing document.md → overwritten with remote content."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        doc_path = tsu_dir / "document.md"
        doc_path.write_text("# Old content\n", encoding="utf-8")
        result = pull(tmp_path, "tech")
        assert result == doc_path
        content = doc_path.read_text()
        assert "Updated content" in content
        assert "Old content" not in content

    @patch("tsu_cli.publisher.fetch_page_html", return_value=None)
    def test_empty_page_raises(self, mock_fetch, tmp_path: Path):
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        with pytest.raises(RuntimeError, match="empty content"):
            pull(tmp_path, "tech")


# ===================================================================
# pull_by_url (standalone pull without init)
# ===================================================================


class TestPullByUrl:
    """Tests for pull_by_url() — standalone pull via direct URL."""

    SAMPLE_URL = "https://acme.atlassian.net/wiki/spaces/DEV/pages/12345/My+Doc"

    def _mock_api(self, html="<p>Remote content</p>"):
        """Return a mock httpx client configured to return the given HTML."""
        client = _mock_client()
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "body": {"storage": {"value": html}},
            "version": {"number": 1},
        }
        client.get.return_value = resp
        return client

    @patch("httpx.Client")
    @patch("tsu_cli.publisher.auth.get_token", return_value="fake-token")
    def test_writes_document_with_page_id(self, mock_token, MockClient, tmp_path: Path):
        """Happy path: fetches page and writes .tsu/document-12345.md."""
        MockClient.return_value = self._mock_api()
        doc_path = pull_by_url(self.SAMPLE_URL, tmp_path)
        assert doc_path.name == "document-12345.md"
        assert doc_path.exists()
        assert "Remote content" in doc_path.read_text()

    @patch("httpx.Client")
    @patch("tsu_cli.publisher.auth.get_token", return_value="fake-token")
    def test_creates_tsu_dir_if_missing(self, mock_token, MockClient, tmp_path: Path):
        """Creates .tsu/ directory when it doesn't exist."""
        tsu_dir = tmp_path / ".tsu"
        assert not tsu_dir.exists()
        MockClient.return_value = self._mock_api()
        doc_path = pull_by_url(self.SAMPLE_URL, tmp_path)
        assert tsu_dir.exists()
        assert doc_path.exists()

    @patch("tsu_cli.publisher.auth.get_token", return_value=None)
    def test_no_credentials_raises(self, mock_token, tmp_path: Path):
        """No token → raises NoCredentialsError."""
        with pytest.raises(NoCredentialsError):
            pull_by_url(self.SAMPLE_URL, tmp_path)

    @patch("httpx.Client")
    @patch("tsu_cli.publisher.auth.get_token", return_value="fake-token")
    def test_empty_content_raises(self, mock_token, MockClient, tmp_path: Path):
        """Empty page body → raises RuntimeError."""
        MockClient.return_value = self._mock_api(html="")
        with pytest.raises(RuntimeError, match="empty content"):
            pull_by_url(self.SAMPLE_URL, tmp_path)

    def test_invalid_url_raises(self, tmp_path: Path):
        """URL without page_id → raises ValueError."""
        with pytest.raises(ValueError, match="Could not extract page_id"):
            pull_by_url("https://acme.atlassian.net/wiki/spaces/DEV", tmp_path)

    @patch("httpx.Client")
    @patch("tsu_cli.publisher.auth.get_token", return_value="fake-token")
    def test_overwrites_existing(self, mock_token, MockClient, tmp_path: Path):
        """Repeated pull overwrites the file."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        (tsu_dir / "document-12345.md").write_text("# Old\n", encoding="utf-8")
        MockClient.return_value = self._mock_api()
        doc_path = pull_by_url(self.SAMPLE_URL, tmp_path)
        content = doc_path.read_text()
        assert "Remote content" in content
        assert "Old" not in content
