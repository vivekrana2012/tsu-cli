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
    safe_write_text,
    seed_prompt,
    validate_write_path,
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
# Path write guard
# ===================================================================


class TestValidateWritePath:
    """Tests for validate_write_path — blocks writes outside .tsu/."""

    def test_inside_tsu(self, tmp_project: Path):
        """Path inside .tsu/ → returns resolved path."""
        target = tmp_project / ".tsu" / "document.md"
        result = validate_write_path(target, tmp_project)
        assert result == target.resolve()

    def test_nested_inside_tsu(self, tmp_project: Path):
        """Nested path inside .tsu/ → returns resolved path."""
        target = tmp_project / ".tsu" / "sub" / "file.md"
        result = validate_write_path(target, tmp_project)
        assert result == target.resolve()

    def test_outside_tsu(self, tmp_project: Path):
        """Path outside .tsu/ → raises ValueError."""
        target = tmp_project / "leaked-file.md"
        with pytest.raises(ValueError, match="Write blocked"):
            validate_write_path(target, tmp_project)

    def test_traversal(self, tmp_project: Path):
        """Path with .. traversal escaping .tsu/ → raises ValueError."""
        target = tmp_project / ".tsu" / ".." / "escape.md"
        with pytest.raises(ValueError, match="Write blocked"):
            validate_write_path(target, tmp_project)

    def test_absolute_outside(self, tmp_path: Path):
        """Absolute path outside project → raises ValueError."""
        target = Path("/tmp/evil.md")
        with pytest.raises(ValueError, match="Write blocked"):
            validate_write_path(target, tmp_path)


class TestSafeWriteText:
    """Tests for safe_write_text — guarded file writing."""

    def test_writes_inside_tsu(self, tmp_project: Path):
        """Write inside .tsu/ succeeds and content is correct."""
        target = tmp_project / ".tsu" / "output.md"
        safe_write_text(target, "hello", tmp_project)
        assert target.read_text(encoding="utf-8") == "hello"

    def test_blocks_outside_tsu(self, tmp_project: Path):
        """Write outside .tsu/ raises ValueError, file not created."""
        target = tmp_project / "bad.md"
        with pytest.raises(ValueError, match="Write blocked"):
            safe_write_text(target, "nope", tmp_project)
        assert not target.exists()


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


# ===================================================================
# seed_prompt auto-matching built-in templates
# ===================================================================


class TestSeedPromptAutoMatch:
    """seed_prompt uses profile-specific built-in templates when available."""

    def test_api_profile_uses_api_template(self, tmp_path: Path):
        """tsu init --profile api_spec seeds from generate-api_spec.md, not generic."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path, profile="api_spec")
        assert path.name == "generate-api_spec.md"
        content = path.read_text(encoding="utf-8")
        # The API template mentions endpoints/schemas, not generic tech overview
        assert "api" in content.lower() or "endpoint" in content.lower()

    def test_func_profile_uses_func_template(self, tmp_path: Path):
        """tsu init --profile func_spec seeds from generate-func_spec.md."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path, profile="func_spec")
        assert path.name == "generate-func_spec.md"
        content = path.read_text(encoding="utf-8")
        assert "business" in content.lower() or "workflow" in content.lower()

    def test_security_profile_uses_security_template(self, tmp_path: Path):
        """tsu init --profile security_spec seeds from generate-security_spec.md."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path, profile="security_spec")
        assert path.name == "generate-security_spec.md"
        content = path.read_text(encoding="utf-8")
        assert "security" in content.lower() or "auth" in content.lower()

    def test_unknown_profile_falls_back_to_generic(self, tmp_path: Path):
        """Unknown profile name falls back to generic generate.md."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path, profile="custom-thing")
        assert path.name == "generate-custom-thing.md"
        content = path.read_text(encoding="utf-8")
        # Should have generic tech overview content
        assert "tech stack" in content.lower() or "architecture" in content.lower()

    def test_auto_match_still_idempotent(self, tmp_path: Path):
        """Existing template is not overwritten even with auto-match."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        path = seed_prompt(tmp_path, profile="api_spec")
        path.write_text("my custom api prompt", encoding="utf-8")

        seed_prompt(tmp_path, profile="api_spec")
        assert path.read_text(encoding="utf-8") == "my custom api prompt"


# ===================================================================
# list_builtin_templates
# ===================================================================


class TestListBuiltinTemplates:
    """list_builtin_templates discovers built-in profile templates."""

    def test_returns_expected_templates(self):
        """Returns api, func, security with descriptions."""
        from tsu_cli.config import list_builtin_templates

        templates = list_builtin_templates()
        assert "api_spec" in templates
        assert "func_spec" in templates
        assert "security_spec" in templates
        # Each has a non-empty description
        for desc in templates.values():
            assert len(desc) > 0

    def test_sorted(self):
        """Templates are returned in sorted order."""
        from tsu_cli.config import list_builtin_templates

        templates = list_builtin_templates()
        keys = list(templates.keys())
        assert keys == sorted(keys)
