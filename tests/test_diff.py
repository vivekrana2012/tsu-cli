"""Tests for tsu_cli.diff — git diff gathering, remote diff, and diff agent."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tsu_cli.diff import (
    _MAX_DIFF_CHARS,
    _check_git_available,
    _diff_output_filename,
    get_diff_output_path,
    get_git_diff,
)


# ===================================================================
# Unit tests — helpers
# ===================================================================


class TestDiffOutputFilename:
    """Filename convention for diff reports."""

    def test_default_profile(self):
        assert _diff_output_filename("tech") == "diff.md"

    def test_custom_profile(self):
        assert _diff_output_filename("api") == "diff-api.md"

    def test_get_path(self, tmp_path: Path):
        path = get_diff_output_path(tmp_path, "tech")
        assert path == tmp_path / ".tsu" / "diff.md"

    def test_get_path_custom_profile(self, tmp_path: Path):
        path = get_diff_output_path(tmp_path, "ops")
        assert path == tmp_path / ".tsu" / "diff-ops.md"


# ===================================================================
# Unit tests — git checks
# ===================================================================


class TestCheckGitAvailable:
    """Tests for _check_git_available."""

    def test_not_a_repo(self, tmp_path: Path):
        """Non-git directory raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Not a git repository"):
            _check_git_available(tmp_path)

    def test_git_not_installed(self, tmp_path: Path):
        """Missing git binary raises RuntimeError."""
        with patch("tsu_cli.diff.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="git is not installed"):
                _check_git_available(tmp_path)

    def test_valid_repo(self, tmp_path: Path):
        """Valid git repo does not raise."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        _check_git_available(tmp_path)  # should not raise


# ===================================================================
# Unit tests — get_git_diff
# ===================================================================


class TestGetGitDiff:
    """Tests for get_git_diff."""

    def test_no_changes(self, tmp_path: Path):
        """Empty diff returns informative message."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        result = get_git_diff(tmp_path, "HEAD")
        assert "No code changes detected" in result

    def test_with_changes(self, tmp_path: Path):
        """Uncommitted changes are captured in the diff."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        # Create a tracked file and modify it
        f = tmp_path / "hello.py"
        f.write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add hello"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
        f.write_text("print('world')\n")

        result = get_git_diff(tmp_path, "HEAD")
        assert "hello.py" in result
        assert "Full Diff" in result

    def test_large_diff_falls_back_to_stat(self, tmp_path: Path):
        """Diffs exceeding _MAX_DIFF_CHARS use stat-only fallback."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        mock_diff = MagicMock()
        mock_diff.stdout = "x" * (_MAX_DIFF_CHARS + 1)

        mock_stat = MagicMock()
        mock_stat.stdout = " 1 file changed, 100 insertions(+)"

        orig_run = subprocess.run

        def patched_run(cmd, **kwargs):
            if "diff" in cmd and "--stat" in cmd:
                return mock_stat
            if "diff" in cmd:
                return mock_diff
            return orig_run(cmd, **kwargs)

        with patch("tsu_cli.diff.subprocess.run", side_effect=patched_run):
            result = get_git_diff(tmp_path, "HEAD")

        assert "too large to include inline" in result
        assert "Full Diff" not in result

    def test_not_a_repo_raises(self, tmp_path: Path):
        """Non-git directory raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Not a git repository"):
            get_git_diff(tmp_path)


# ===================================================================
# Integration tests — mocked CopilotClient for run_diff
# ===================================================================


def _make_mock_copilot(response_text: str = "## What's Stale\nNothing.\n\n## What's New\nNothing.\n\n## What's Wrong\nNothing."):
    """Create mock CopilotClient for diff tests."""

    class MockEvent:
        def __init__(self, type_val, content=""):
            self.type = MagicMock(value=type_val)
            self.data = MagicMock(content=content)

    class MockSession:
        def __init__(self):
            self._on_cb = None

        def on(self, cb):
            self._on_cb = cb

        async def send(self, msg):
            if self._on_cb:
                self._on_cb(MockEvent("assistant.message", response_text))
                self._on_cb(MockEvent("session.idle"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        async def create_session(self, *args, **kwargs):
            return MockSession()

    return MockClient


class TestRunDiff:
    """Tests for run_diff with mocked CopilotClient."""

    def test_writes_report(self, tmp_project: Path):
        """run_diff writes diff report file."""
        # Create a document for the agent to read
        doc_path = tmp_project / ".tsu" / "document.md"
        doc_path.write_text("# My Doc\n\nSome content.\n")

        MockClient = _make_mock_copilot(
            "## What's Stale\nSection A is outdated.\n\n"
            "## What's New\nNew endpoint /api/v2.\n\n"
            "## What's Wrong\nNo issues detected."
        )

        with (
            patch("tsu_cli.diff.CopilotClient", MockClient),
            patch("tsu_cli.diff._SubprocessConfig", None),
            patch("tsu_cli.diff.Live"),
            patch("tsu_cli.diff.console"),
        ):
            from tsu_cli.diff import run_diff
            result = run_diff(
                tmp_project,
                change_context="Some git diff context",
                model="gpt-4o",
            )

        assert result.exists()
        assert result.name == "diff.md"
        content = result.read_text()
        assert "What's Stale" in content
        assert "What's New" in content
        assert "What's Wrong" in content

    def test_strips_code_fences(self, tmp_project: Path):
        """Response wrapped in code fences → stripped."""
        doc_path = tmp_project / ".tsu" / "document.md"
        doc_path.write_text("# Doc\n")

        raw = "```markdown\n## What's Stale\nNothing.\n\n## What's New\nNothing.\n\n## What's Wrong\nNothing.\n```"
        MockClient = _make_mock_copilot(raw)

        with (
            patch("tsu_cli.diff.CopilotClient", MockClient),
            patch("tsu_cli.diff._SubprocessConfig", None),
            patch("tsu_cli.diff.Live"),
            patch("tsu_cli.diff.console"),
        ):
            from tsu_cli.diff import run_diff
            result = run_diff(
                tmp_project,
                change_context="context",
                model="gpt-4o",
            )

        content = result.read_text()
        assert "```markdown" not in content
        assert "## What's Stale" in content

    def test_profile_output_path(self, tmp_project_with_profiles: Path):
        """Profile 'ops' → diff-ops.md."""
        doc_path = tmp_project_with_profiles / ".tsu" / "document-ops.md"
        doc_path.write_text("# Ops Doc\n")

        MockClient = _make_mock_copilot()

        with (
            patch("tsu_cli.diff.CopilotClient", MockClient),
            patch("tsu_cli.diff._SubprocessConfig", None),
            patch("tsu_cli.diff.Live"),
            patch("tsu_cli.diff.console"),
        ):
            from tsu_cli.diff import run_diff
            result = run_diff(
                tmp_project_with_profiles,
                change_context="context",
                model="gpt-4o",
                profile="ops",
            )

        assert result.name == "diff-ops.md"
        assert result.exists()


# ===================================================================
# CLI integration tests
# ===================================================================


class TestDiffCLI:
    """Tests for the tsu diff CLI command."""

    def test_no_init(self, cli_runner, tmp_path):
        """Error when .tsu/ not initialized."""
        from tsu_cli.main import app
        result = cli_runner.invoke(app, ["diff", "--dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "not initialized" in result.output

    def test_no_document(self, cli_runner, tmp_project):
        """Error when document.md doesn't exist."""
        from tsu_cli.main import app
        result = cli_runner.invoke(app, ["diff", "--dir", str(tmp_project)])
        assert result.exit_code != 0
        assert "No document found" in result.output

    def test_remote_no_page_id(self, cli_runner, tmp_project):
        """Error when --remote used but no page_id configured."""
        # Create a document so we pass that check
        (tmp_project / ".tsu" / "document.md").write_text("# Doc\n")
        from tsu_cli.main import app
        result = cli_runner.invoke(app, ["diff", "--remote", "--dir", str(tmp_project)])
        assert result.exit_code != 0
        assert "No page_id" in result.output

    def test_git_not_available(self, cli_runner, tmp_project):
        """Error when not in a git repo (code diff mode)."""
        (tmp_project / ".tsu" / "document.md").write_text("# Doc\n")
        from tsu_cli.main import app
        result = cli_runner.invoke(app, ["diff", "--dir", str(tmp_project)])
        assert result.exit_code != 0
        assert "Not a git repository" in result.output
