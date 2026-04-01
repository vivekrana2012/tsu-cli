"""Tests for tsu CLI commands via Typer CliRunner (E2E with mocked deps)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tsu_cli.main import app


@pytest.fixture
def runner():
    return CliRunner()


# ===================================================================
# Helper
# ===================================================================


def _init_tsu(project_dir: Path, profile: str = "tech", page_title: str | None = None):
    """Manually create .tsu/ scaffold (bypasses interactive prompts)."""
    tsu_dir = project_dir / ".tsu"
    tsu_dir.mkdir(exist_ok=True)

    (tsu_dir / "config.json").write_text(
        json.dumps({"model": "gpt-4o"}, indent=2) + "\n", encoding="utf-8",
    )

    from tsu_cli.config import _confluence_filename, _prompt_filename

    conf_data = {
        "parent_page_url": "https://example.atlassian.net/wiki/spaces/ENG/pages/111/Parent",
        "page_title": page_title or f"TestProject - {profile.capitalize()}",
        "page_id": None,
    }
    (tsu_dir / _confluence_filename(profile)).write_text(
        json.dumps(conf_data, indent=2) + "\n", encoding="utf-8",
    )

    (tsu_dir / _prompt_filename(profile)).write_text(
        f"# {profile} Prompt\nAnalyze the project.\n"
        "{{ additional_instructions }}\n"
        "{{ existing_document }}\n",
        encoding="utf-8",
    )


# ===================================================================
# tsu init
# ===================================================================


class TestInit:
    """Tests #75-79: tsu init CLI command."""

    @patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o"])
    @patch("tsu_cli.main.publisher.create_blank_page", return_value="new1")
    def test_creates_tsu_dir(self, mock_blank, mock_models, runner: CliRunner, tmp_path: Path):
        """#75 tsu init creates .tsu/ with config.json, confluence.json, generate.md."""
        result = runner.invoke(
            app,
            ["init", "--dir", str(tmp_path)],
            input="gpt-4o\n\nTest Title\n",
        )
        assert result.exit_code == 0 or result.exit_code is None
        tsu_dir = tmp_path / ".tsu"
        assert (tsu_dir / "config.json").exists()
        assert (tsu_dir / "confluence.json").exists()
        assert (tsu_dir / "generate.md").exists()

    @patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o"])
    @patch("tsu_cli.main.publisher.create_blank_page", return_value="new1")
    def test_custom_profile(self, mock_blank, mock_models, runner: CliRunner, tmp_path: Path):
        """#76 tsu init --profile ops creates profile-specific files."""
        # First init tech profile
        _init_tsu(tmp_path, "tech")

        result = runner.invoke(
            app,
            ["init", "--dir", str(tmp_path), "--profile", "ops"],
            input="\nOps Title\n",
        )
        tsu_dir = tmp_path / ".tsu"
        assert (tsu_dir / "confluence-ops.json").exists()
        assert (tsu_dir / "generate-ops.md").exists()
        # Tech files untouched
        assert (tsu_dir / "confluence.json").exists()
        assert (tsu_dir / "generate.md").exists()

    def test_preserves_page_id(self, runner: CliRunner, tmp_path: Path):
        """#77 Re-init with existing page_id → preserved in config."""
        _init_tsu(tmp_path, "tech")
        tsu_dir = tmp_path / ".tsu"

        # Set a page_id manually
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["page_id"] = "preserved123"
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")

        with patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o"]):
            result = runner.invoke(
                app,
                ["init", "--dir", str(tmp_path)],
                input="y\ngpt-4o\n\nRe-init Title\n",
            )

        conf_after = json.loads((tsu_dir / "confluence.json").read_text())
        assert conf_after["page_id"] == "preserved123"

    @patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o"])
    def test_default_page_title_tech(self, mock_models, runner: CliRunner, tmp_path: Path):
        """#78 --profile tech → title contains 'Tech Overview'."""
        result = runner.invoke(
            app,
            ["init", "--dir", str(tmp_path)],
            input="gpt-4o\n\n\n",
        )
        tsu_dir = tmp_path / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        assert "Tech Overview" in conf["page_title"]

    @patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o"])
    def test_default_page_title_custom(self, mock_models, runner: CliRunner, tmp_path: Path):
        """#79 --profile func → title contains 'Func'."""
        _init_tsu(tmp_path, "tech")  # need existing .tsu/
        result = runner.invoke(
            app,
            ["init", "--dir", str(tmp_path), "--profile", "func"],
            input="\n\n",
        )
        tsu_dir = tmp_path / ".tsu"
        conf = json.loads((tsu_dir / "confluence-func.json").read_text())
        assert "Func" in conf["page_title"]


# ===================================================================
# tsu generate
# ===================================================================


class TestGenerate:
    """Tests #80-81: tsu generate CLI command."""

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.fetch_page_html", return_value=None)
    def test_offline(self, mock_fetch, mock_gen, runner: CliRunner, tmp_path: Path):
        """#80 tsu generate --offline → calls generator.generate."""
        _init_tsu(tmp_path)
        mock_gen.return_value = tmp_path / ".tsu" / "document.md"

        result = runner.invoke(
            app,
            ["generate", "--dir", str(tmp_path), "--offline"],
        )
        mock_gen.assert_called_once()

    def test_profile_not_found(self, runner: CliRunner, tmp_path: Path):
        """#81 tsu generate --profile nonexistent → exit code 1."""
        _init_tsu(tmp_path)  # only tech profile

        result = runner.invoke(
            app,
            ["generate", "--dir", str(tmp_path), "--profile", "nonexistent"],
        )
        assert result.exit_code != 0
        assert "not found" in result.stdout.lower() or "not found" in (result.stderr or "").lower()


# ===================================================================
# tsu push
# ===================================================================


class TestPush:
    """Tests #82-83: tsu push CLI command."""

    @patch("tsu_cli.main.publisher.push", return_value="https://example.atlassian.net/wiki/pages/123")
    def test_success(self, mock_push, runner: CliRunner, tmp_path: Path):
        """#82 tsu push → calls publisher.push."""
        _init_tsu(tmp_path)

        result = runner.invoke(
            app,
            ["push", "--dir", str(tmp_path)],
        )
        mock_push.assert_called_once()

    def test_not_initialized(self, runner: CliRunner, tmp_path: Path):
        """#83 tsu push without .tsu/ → exit code 1."""
        result = runner.invoke(
            app,
            ["push", "--dir", str(tmp_path)],
        )
        assert result.exit_code != 0


# ===================================================================
# tsu list-profiles
# ===================================================================


class TestListProfiles:
    """Tests #84-85: tsu list-profiles CLI command."""

    def test_output(self, runner: CliRunner, tmp_path: Path):
        """#84 Seed tech + ops profiles → both appear in output."""
        _init_tsu(tmp_path, "tech", page_title="Tech Overview")
        _init_tsu(tmp_path, "ops", page_title="Ops Guide")

        result = runner.invoke(
            app,
            ["list-profiles", "--dir", str(tmp_path)],
        )
        assert result.exit_code == 0 or result.exit_code is None
        assert "tech" in result.stdout.lower()
        assert "ops" in result.stdout.lower()

    def test_multi_profile_table(self, runner: CliRunner, tmp_path: Path):
        """#85 Init two profiles with different titles → correct titles shown."""
        _init_tsu(tmp_path, "tech", page_title="My Tech Docs")
        _init_tsu(tmp_path, "ops", page_title="Operations Runbook")

        result = runner.invoke(
            app,
            ["list-profiles", "--dir", str(tmp_path)],
        )
        assert "My Tech Docs" in result.stdout
        assert "Operations Runbook" in result.stdout


# ===================================================================
# tsu models
# ===================================================================


class TestModels:
    """Test #86: tsu models CLI command."""

    @patch("tsu_cli.main.generator.list_models", return_value=["gpt-4o", "claude-sonnet-4.5"])
    def test_lists_models(self, mock_models, runner: CliRunner):
        """#86 Mock Copilot SDK → model list printed."""
        result = runner.invoke(app, ["models"])
        assert "gpt-4o" in result.stdout
        assert "claude-sonnet-4.5" in result.stdout


# ===================================================================
# tsu auth
# ===================================================================


class TestAuthSet:
    """Test #87: tsu auth set."""

    @patch("tsu_cli.main.auth.set_credentials")
    def test_stores(self, mock_set, runner: CliRunner):
        """#87 Mock typer.prompt + keyring → credentials stored."""
        result = runner.invoke(
            app,
            ["auth", "set"],
            input="user@example.com\nmy-secret-token\n",
        )
        mock_set.assert_called_once_with("user@example.com", "my-secret-token")


class TestAuthClear:
    """Test #88: tsu auth clear."""

    @patch("tsu_cli.main.auth.clear_credentials")
    def test_clears(self, mock_clear, runner: CliRunner):
        """#88 Mock confirm + keyring → credentials removed."""
        result = runner.invoke(
            app,
            ["auth", "clear"],
            input="y\n",
        )
        mock_clear.assert_called_once()


class TestAuthStatus:
    """Test #89: tsu auth status."""

    @patch("tsu_cli.main.auth.get_status", return_value={"token": "keyring", "user": "env"})
    def test_shows_status(self, mock_status, runner: CliRunner):
        """#89 Mock get_status → formatted table output."""
        result = runner.invoke(app, ["auth", "status"])
        assert "keyring" in result.stdout.lower()
        assert "env" in result.stdout.lower()


# ===================================================================
# Error paths
# ===================================================================


class TestErrorPaths:
    """Test #90: generate not initialized."""

    def test_generate_not_initialized(self, runner: CliRunner, tmp_path: Path):
        """#90 tsu generate without .tsu/ → abort."""
        result = runner.invoke(
            app,
            ["generate", "--dir", str(tmp_path)],
        )
        assert result.exit_code != 0
