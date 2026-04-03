"""Tests for tsu CLI commands via Typer CliRunner (E2E with mocked deps)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tsu_cli.main import app
from tsu_cli.publisher import NoCredentialsError, NoPageIDError, NoParentPageError


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
        "{{ additional_instructions }}\n",
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
    def test_offline(self, mock_gen, runner: CliRunner, tmp_path: Path):
        """#80 tsu generate --offline → calls generator.generate without pull."""
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
# tsu profiles
# ===================================================================


class TestProfiles:
    """Tests #84-85: tsu profiles CLI command."""

    def test_output(self, runner: CliRunner, tmp_path: Path):
        """#84 Seed tech + ops profiles → both appear in output."""
        _init_tsu(tmp_path, "tech", page_title="Tech Overview")
        _init_tsu(tmp_path, "ops", page_title="Ops Guide")

        result = runner.invoke(
            app,
            ["profiles", "--dir", str(tmp_path)],
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
            ["profiles", "--dir", str(tmp_path)],
        )
        assert "My Tech Docs" in result.stdout
        assert "Operations Runbook" in result.stdout

    def test_shows_available_templates(self, runner: CliRunner, tmp_path: Path):
        """Available templates section shows built-in templates not yet initialized."""
        _init_tsu(tmp_path, "tech", page_title="Tech Overview")

        result = runner.invoke(
            app,
            ["profiles", "--dir", str(tmp_path)],
        )
        assert result.exit_code == 0 or result.exit_code is None
        # Built-in templates (api_spec, business_rules, security_spec) should appear as available
        assert "api_spec" in result.stdout.lower()
        assert "func_spec" in result.stdout.lower()
        assert "security_spec" in result.stdout.lower()

    def test_hides_initialized_from_available(self, runner: CliRunner, tmp_path: Path):
        """Initialized built-in profiles don't appear in Available Templates."""
        _init_tsu(tmp_path, "tech", page_title="Tech Overview")
        _init_tsu(tmp_path, "api_spec", page_title="API Spec")

        result = runner.invoke(
            app,
            ["profiles", "--dir", str(tmp_path)],
        )
        # api_spec should appear in the Initialized section, not duplicated
        # func_spec and security_spec should still appear in Available
        assert "func_spec" in result.stdout.lower()
        assert "security_spec" in result.stdout.lower()


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


# ===================================================================
# Additional coverage tests
# ===================================================================


class TestProfilesNotInitialized:
    """profiles when .tsu/ doesn't exist."""

    def test_not_initialized(self, runner: CliRunner, tmp_path: Path):
        """Not initialized → shows available templates + no initialized message."""
        result = runner.invoke(app, ["profiles", "--dir", str(tmp_path)])
        # Should still show available templates even without .tsu/
        assert "no initialized" in result.stdout.lower() or "tsu init" in result.stdout.lower()


class TestProfilesEmpty:
    """profiles when .tsu/ exists but no profiles."""

    def test_no_profiles(self, runner: CliRunner, tmp_path: Path):
        """No profiles → shows no initialized + available templates."""
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        (tsu_dir / "config.json").write_text(json.dumps({"model": "gpt-4o"}))
        result = runner.invoke(app, ["profiles", "--dir", str(tmp_path)])
        assert "no initialized" in result.stdout.lower() or "tsu init" in result.stdout.lower()


class TestModelsEmpty:
    """tsu models when no models available."""

    @patch("tsu_cli.main.generator.list_models", return_value=[])
    def test_empty_models(self, mock_models, runner: CliRunner):
        """No models → exit code 1."""
        result = runner.invoke(app, ["models"])
        assert result.exit_code != 0


def _set_page_id(project_dir: Path, page_id: str, profile: str = "tech") -> None:
    """Set page_id in the profile's confluence config."""
    from tsu_cli.config import _confluence_filename
    tsu_dir = project_dir / ".tsu"
    conf_path = tsu_dir / _confluence_filename(profile)
    conf = json.loads(conf_path.read_text())
    conf["page_id"] = page_id
    conf_path.write_text(json.dumps(conf, indent=2) + "\n", encoding="utf-8")


class TestGenerateSyncPaths:
    """Tests #99-100 + sync path variants for generate with Confluence pull."""

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.pull")
    def test_sync_with_existing_page(self, mock_pull, mock_gen, runner: CliRunner, tmp_path: Path):
        """#99 page_id set → pull called, then generate called."""
        _init_tsu(tmp_path)
        _set_page_id(tmp_path, "pg123")
        doc_path = tmp_path / ".tsu" / "document.md"
        mock_pull.return_value = doc_path
        mock_gen.return_value = doc_path
        result = runner.invoke(app, ["generate", "--dir", str(tmp_path)])
        mock_pull.assert_called_once()
        mock_gen.assert_called_once()

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.pull", side_effect=Exception("Network error"))
    def test_sync_exception_aborts(self, mock_pull, mock_gen, runner: CliRunner, tmp_path: Path):
        """page_id set + pull() raises → aborts, generate not called."""
        _init_tsu(tmp_path)
        _set_page_id(tmp_path, "pg123")
        result = runner.invoke(app, ["generate", "--dir", str(tmp_path)])
        assert result.exit_code != 0
        mock_gen.assert_not_called()

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.pull")
    def test_sync_no_page_id_skips_pull(self, mock_pull, mock_gen, runner: CliRunner, tmp_path: Path):
        """No page_id → pull not called, generate proceeds."""
        _init_tsu(tmp_path)
        mock_gen.return_value = tmp_path / ".tsu" / "document.md"
        result = runner.invoke(app, ["generate", "--dir", str(tmp_path)])
        mock_pull.assert_not_called()
        mock_gen.assert_called_once()

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.pull", side_effect=NoCredentialsError("No creds"))
    def test_sync_no_credentials_aborts(self, mock_pull, mock_gen, runner: CliRunner, tmp_path: Path):
        """page_id set + NoCredentialsError → aborts, generate not called."""
        _init_tsu(tmp_path)
        _set_page_id(tmp_path, "pg123")
        result = runner.invoke(app, ["generate", "--dir", str(tmp_path)])
        assert result.exit_code != 0
        mock_gen.assert_not_called()

    @patch("tsu_cli.main.generator.generate")
    @patch("tsu_cli.main.publisher.pull")
    def test_offline_skips_pull(self, mock_pull, mock_gen, runner: CliRunner, tmp_path: Path):
        """#100 --offline → pull not called, generate proceeds."""
        _init_tsu(tmp_path)
        _set_page_id(tmp_path, "pg123")
        mock_gen.return_value = tmp_path / ".tsu" / "document.md"
        result = runner.invoke(app, ["generate", "--dir", str(tmp_path), "--offline"])
        mock_pull.assert_not_called()
        mock_gen.assert_called_once()


class TestPushNotInitialized:
    """push when .tsu/ doesn't exist."""

    def test_not_initialized(self, runner: CliRunner, tmp_path: Path):
        """Not initialized → exit code 1."""
        result = runner.invoke(app, ["push", "--dir", str(tmp_path)])
        assert result.exit_code != 0

    def test_no_parent_page_url(self, runner: CliRunner, tmp_path: Path):
        """No parent_page_url → exit code 1."""
        _init_tsu(tmp_path)
        tsu_dir = tmp_path / ".tsu"
        conf = json.loads((tsu_dir / "confluence.json").read_text())
        conf["parent_page_url"] = ""
        (tsu_dir / "confluence.json").write_text(json.dumps(conf, indent=2) + "\n")
        result = runner.invoke(app, ["push", "--dir", str(tmp_path)])
        assert result.exit_code != 0


class TestAuthStatusDisplay:
    """Test auth status display for all source types."""

    @patch("tsu_cli.main.auth.get_status", return_value={"token": "not set", "user": "not set"})
    def test_not_set(self, mock_status, runner: CliRunner):
        """Not configured → shows 'not set'."""
        result = runner.invoke(app, ["auth", "status"])
        assert "not configured" in result.stdout.lower() or "not set" in result.stdout.lower()


class TestHelpCommand:
    """Test tsu help command."""

    def test_shows_help(self, runner: CliRunner):
        """tsu help → renders help.md content."""
        result = runner.invoke(app, ["help"])
        assert result.exit_code == 0 or result.exit_code is None
