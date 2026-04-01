"""Tests for tsu_cli.config — config I/O, filenames, profiles, seed_prompt."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tsu_cli.config import (
    DEFAULT_PROFILE,
    _confluence_filename,
    _document_filename,
    _prompt_filename,
    get_document_path,
    get_prompt_path,
    is_initialized,
    list_profiles,
    read_config,
    read_confluence,
    seed_prompt,
    write_config,
    write_confluence,
)


# ===================================================================
# Filename helpers
# ===================================================================


class TestFilenameHelpers:
    """Tests #12-17: filename generation for profiles."""

    def test_confluence_filename_default(self):
        """#12 tech profile → legacy 'confluence.json'."""
        assert _confluence_filename("tech") == "confluence.json"

    def test_confluence_filename_custom(self):
        """#13 custom profile → 'confluence-ops.json'."""
        assert _confluence_filename("ops") == "confluence-ops.json"

    def test_prompt_filename_default(self):
        """#14 tech profile → 'generate.md'."""
        assert _prompt_filename("tech") == "generate.md"

    def test_prompt_filename_custom(self):
        """#15 custom profile → 'generate-func.md'."""
        assert _prompt_filename("func") == "generate-func.md"

    def test_document_filename_default(self):
        """#16 tech profile → 'document.md'."""
        assert _document_filename("tech") == "document.md"

    def test_document_filename_custom(self):
        """#17 custom profile → 'document-api.md'."""
        assert _document_filename("api") == "document-api.md"


# ===================================================================
# Config read/write
# ===================================================================


class TestConfigReadWrite:
    """Tests #18-19: config.json round-trip and defaults."""

    def test_roundtrip(self, tmp_project: Path):
        """#18 Write then read config.json — data preserved."""
        data = {"model": "claude-sonnet-4.5"}
        write_config(data, tmp_project)
        result = read_config(tmp_project)
        assert result["model"] == "claude-sonnet-4.5"

    def test_defaults(self, tmp_path: Path):
        """#19 read_config on dir without config.json → DEFAULT_CONFIG."""
        # tmp_path has no .tsu/ at all
        result = read_config(tmp_path)
        assert result["model"] == "gpt-4o"


# ===================================================================
# Confluence config read/write
# ===================================================================


class TestConfluenceReadWrite:
    """Tests #20-21: confluence config round-trip with profiles."""

    def test_roundtrip_default(self, tmp_project: Path):
        """#20 Write/read confluence.json for default 'tech' profile."""
        data = {"parent_page_url": "https://x.atlassian.net/wiki/spaces/A/pages/1/P", "page_title": "T", "page_id": "42"}
        write_confluence(data, tmp_project)
        result = read_confluence(tmp_project)
        assert result["page_id"] == "42"

    def test_roundtrip_custom_profile(self, tmp_project: Path):
        """#21 Write/read confluence-ops.json for 'ops' profile."""
        data = {"parent_page_url": "https://x.atlassian.net/wiki/spaces/B/pages/2/P", "page_title": "Ops", "page_id": "77"}
        write_confluence(data, tmp_project, profile="ops")
        result = read_confluence(tmp_project, profile="ops")
        assert result["page_id"] == "77"
        assert result["page_title"] == "Ops"

        # Tech profile not affected
        tech = read_confluence(tmp_project)
        assert tech["page_id"] is None  # from fixture


# ===================================================================
# Profile listing
# ===================================================================


class TestListProfiles:
    """Tests #22-23: list_profiles discovery."""

    def test_multiple_profiles(self, tmp_project: Path):
        """#22 Discovers tech + func + api profiles, sorted."""
        tsu_dir = tmp_project / ".tsu"
        (tsu_dir / "generate-func.md").write_text("func prompt", encoding="utf-8")
        (tsu_dir / "generate-api.md").write_text("api prompt", encoding="utf-8")

        profiles = list_profiles(tmp_project)
        assert profiles == ["api", "func", "tech"]

    def test_empty(self, tmp_path: Path):
        """#23 No .tsu/ → empty list."""
        assert list_profiles(tmp_path) == []


# ===================================================================
# is_initialized
# ===================================================================


class TestIsInitialized:
    """Tests #24-25: is_initialized check."""

    def test_true(self, tmp_project: Path):
        """#24 With config.json → True."""
        assert is_initialized(tmp_project) is True

    def test_false(self, tmp_path: Path):
        """#25 Without config.json → False."""
        assert is_initialized(tmp_path) is False


# ===================================================================
# seed_prompt
# ===================================================================


class TestSeedPrompt:
    """Tests #26-27: seed_prompt file creation."""

    def test_creates_file(self, tmp_path: Path):
        """#26 seed_prompt creates prompt file from built-in template."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert len(content) > 0  # has content from built-in

    def test_idempotent(self, tmp_path: Path):
        """#27 Second call doesn't overwrite edited file."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path)

        # Edit the file
        path.write_text("custom content", encoding="utf-8")

        # Re-seed — should NOT overwrite
        seed_prompt(tmp_path)
        assert path.read_text(encoding="utf-8") == "custom content"


# ===================================================================
# Path helpers with profiles
# ===================================================================


class TestPathHelpers:
    """Tests #28-29: get_document_path and get_prompt_path with profiles."""

    def test_document_path_custom(self, tmp_project: Path):
        """#28 get_document_path with 'func' → .tsu/document-func.md."""
        p = get_document_path(tmp_project, "func")
        assert p.name == "document-func.md"
        assert p.parent.name == ".tsu"

    def test_prompt_path_custom(self, tmp_project: Path):
        """#29 get_prompt_path with 'ops' → .tsu/generate-ops.md."""
        p = get_prompt_path(tmp_project, "ops")
        assert p.name == "generate-ops.md"
        assert p.parent.name == ".tsu"


# ===================================================================
# Profile isolation and backward compatibility
# ===================================================================


class TestProfileIsolation:
    """Tests #30-31: multi-profile isolation and tech backward compat."""

    def test_multi_profile_isolation(self, tmp_project: Path):
        """#30 Writing to ops profile doesn't affect tech profile."""
        # Write ops profile
        ops_data = {"parent_page_url": "https://x/ops", "page_title": "Ops", "page_id": "333"}
        write_confluence(ops_data, tmp_project, profile="ops")

        # Tech profile unchanged
        tech_data = read_confluence(tmp_project, profile="tech")
        assert tech_data["page_id"] is None
        assert tech_data["page_title"] == "TestProject - Tech Overview"

        # Ops profile correct
        ops_read = read_confluence(tmp_project, profile="ops")
        assert ops_read["page_id"] == "333"

    def test_tech_backward_compat(self, tmp_project: Path):
        """#31 Tech profile uses legacy filenames (no -tech suffix)."""
        tsu_dir = tmp_project / ".tsu"

        # Verify the actual files on disk use legacy names
        assert (tsu_dir / "confluence.json").exists()
        assert (tsu_dir / "generate.md").exists()
        assert not (tsu_dir / "confluence-tech.json").exists()
        assert not (tsu_dir / "generate-tech.md").exists()

        # Functions still work transparently
        data = read_confluence(tmp_project, profile="tech")
        assert data["page_title"] == "TestProject - Tech Overview"
