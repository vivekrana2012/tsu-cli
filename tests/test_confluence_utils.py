"""Tests for tsu_cli.confluence_utils — URL parsing and API resolution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tsu_cli.confluence_utils import (
    extract_base_url,
    extract_page_id_from_url,
    extract_space_and_title_from_url,
    extract_space_key_from_url,
    get_page_id_by_space_and_title,
    get_space_key_from_page,
    resolve_page_id,
)


# ===================================================================
# Unit tests — pure URL parsing (no mocks)
# ===================================================================


class TestExtractBaseUrl:
    """Tests #1-3: extract_base_url."""

    def test_cloud_url(self):
        """#1 Cloud URLs include /wiki prefix."""
        url = "https://example.atlassian.net/wiki/spaces/ENG/pages/123/Title"
        assert extract_base_url(url) == "https://example.atlassian.net/wiki"

    def test_server_url(self):
        """#2 Server URLs without /wiki → scheme + host only."""
        url = "https://confluence.example.com/display/ENG/Page"
        assert extract_base_url(url) == "https://confluence.example.com"

    def test_trailing_slash(self):
        """#3 Trailing slashes stripped."""
        url = "https://example.atlassian.net/wiki/"
        result = extract_base_url(url)
        assert not result.endswith("/")
        assert result == "https://example.atlassian.net/wiki"


class TestExtractPageIdFromUrl:
    """Tests #4-6: extract_page_id_from_url."""

    def test_query_param(self):
        """#4 ?pageId=123 → '123'."""
        url = "https://example.atlassian.net/wiki/pages/viewpage.action?pageId=12345"
        assert extract_page_id_from_url(url) == "12345"

    def test_path_segment(self):
        """#5 /pages/123/Title → '123'."""
        url = "https://example.atlassian.net/wiki/spaces/ENG/pages/67890/My+Page"
        assert extract_page_id_from_url(url) == "67890"

    def test_no_page_id(self):
        """#6 No page ID in URL → None."""
        url = "https://example.atlassian.net/wiki/display/ENG/Page"
        assert extract_page_id_from_url(url) is None


class TestExtractSpaceAndTitle:
    """Tests #7-8: extract_space_and_title_from_url."""

    def test_display_url(self):
        """#7 /display/SPACE/My+Title → ('SPACE', 'My Title')."""
        url = "https://example.atlassian.net/wiki/display/ENG/My+Title"
        space, title = extract_space_and_title_from_url(url)
        assert space == "ENG"
        assert title == "My Title"

    def test_no_display(self):
        """#8 Non-display URL → (None, None)."""
        url = "https://example.atlassian.net/wiki/spaces/ENG/pages/123"
        space, title = extract_space_and_title_from_url(url)
        assert space is None
        assert title is None


class TestExtractSpaceKey:
    """Tests #9-11: extract_space_key_from_url."""

    def test_spaces_format(self):
        """#9 /spaces/KEY/pages/... → 'KEY'."""
        url = "https://example.atlassian.net/wiki/spaces/DEV/pages/123/Title"
        assert extract_space_key_from_url(url) == "DEV"

    def test_display_format(self):
        """#10 /display/KEY/Title → 'KEY'."""
        url = "https://confluence.example.com/display/OPS/My+Page"
        assert extract_space_key_from_url(url) == "OPS"

    def test_no_space_key(self):
        """#11 No space key in URL → None."""
        url = "https://example.atlassian.net/wiki/pages/viewpage.action?pageId=123"
        assert extract_space_key_from_url(url) is None


# ===================================================================
# Integration tests — mocked httpx
# ===================================================================


class TestGetPageIdBySpaceAndTitle:
    """Tests #51-52: get_page_id_by_space_and_title (mocked httpx)."""

    def test_found(self):
        """#51 Mock search API returns page ID."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [{"id": "99999"}]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("tsu_cli.confluence_utils.httpx.Client", return_value=mock_client):
            result = get_page_id_by_space_and_title(
                "https://example.atlassian.net/wiki", "ENG", "My Page",
                bearer_token="tok",
            )
        assert result == "99999"

    def test_not_found(self):
        """#52 Empty results → raises Exception."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("tsu_cli.confluence_utils.httpx.Client", return_value=mock_client):
            with pytest.raises(Exception, match="No page found"):
                get_page_id_by_space_and_title(
                    "https://example.atlassian.net/wiki", "ENG", "Missing",
                    bearer_token="tok",
                )


class TestResolvePageId:
    """Tests #53-55: resolve_page_id."""

    def test_direct_from_url(self):
        """#53 URL with pageId → resolves without API call."""
        base, pid = resolve_page_id(
            "https://example.atlassian.net/wiki/spaces/ENG/pages/555/Title"
        )
        assert base == "https://example.atlassian.net/wiki"
        assert pid == "555"

    def test_via_search(self):
        """#54 Display URL → falls back to API search."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": [{"id": "777"}]}
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("tsu_cli.confluence_utils.httpx.Client", return_value=mock_client):
            base, pid = resolve_page_id(
                "https://confluence.example.com/display/ENG/My+Page",
                bearer_token="tok",
            )
        assert base == "https://confluence.example.com"
        assert pid == "777"

    def test_fails(self):
        """#55 No ID, no space/title → raises Exception."""
        with pytest.raises(Exception, match="Could not resolve"):
            resolve_page_id(
                "https://example.atlassian.net/wiki/x/shortcode",
            )


class TestGetSpaceKeyFromPage:
    """Test #56: get_space_key_from_page (mocked httpx)."""

    def test_returns_space_key(self):
        """#56 Mock API → returns space key."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"space": {"key": "DEV"}}

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("tsu_cli.confluence_utils.httpx.Client", return_value=mock_client):
            result = get_space_key_from_page(
                "https://example.atlassian.net/wiki", "123",
                bearer_token="tok",
            )
        assert result == "DEV"
