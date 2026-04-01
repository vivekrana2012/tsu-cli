"""Tests for tsu_cli.generator — model validation and mocked generation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tsu_cli.generator import validate_model


# ===================================================================
# Unit tests — validate_model
# ===================================================================


class TestValidateModel:
    """Tests #47-50: validate_model."""

    def test_match(self):
        """#47 Model in list → True."""
        assert validate_model("gpt-4o", ["gpt-4o", "claude-sonnet-4.5"]) is True

    def test_case_insensitive(self):
        """#48 Case-insensitive match → True."""
        assert validate_model("GPT-4O", ["gpt-4o", "claude-sonnet-4.5"]) is True

    def test_missing(self):
        """#49 Unknown model → False."""
        assert validate_model("unknown", ["gpt-4o", "claude-sonnet-4.5"]) is False

    def test_empty_list(self):
        """#50 Empty available list → True (can't validate)."""
        assert validate_model("anything", []) is True


# ===================================================================
# Integration tests — mocked CopilotClient
# ===================================================================


def _make_mock_copilot(response_text: str = "# Generated Doc\n\nContent here."):
    """Create mock CopilotClient that returns a canned response."""

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
            # Simulate assistant.message then session.idle
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

        async def create_session(self, config):
            return MockSession()

        async def list_models(self):
            return ["gpt-4o", "claude-sonnet-4.5"]

    return MockClient


class TestListModels:
    """Test #70: list_models."""

    def test_returns_models(self):
        """#70 Mock CopilotClient → returns model list."""
        MockClient = _make_mock_copilot()

        with patch("tsu_cli.generator.CopilotClient", MockClient):
            from tsu_cli.generator import list_models
            # Suppress Rich spinner output
            with patch("tsu_cli.generator.Live"):
                result = list_models()
        assert "gpt-4o" in result
        assert "claude-sonnet-4.5" in result


class TestGenerate:
    """Tests #71-74: generate with mocked CopilotClient."""

    def test_writes_document(self, tmp_project: Path):
        """#71 Mock CopilotClient → output file written."""
        MockClient = _make_mock_copilot("# Generated\n\nHello world.")

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            result = generate(tmp_project, model="gpt-4o", profile="tech")

        assert result.exists()
        content = result.read_text()
        assert "Generated" in content
        assert "Hello world" in content

    def test_strips_code_fences(self, tmp_project: Path):
        """#72 Response wrapped in ```markdown → fences stripped."""
        raw = "```markdown\n# Doc\nContent\n```"
        MockClient = _make_mock_copilot(raw)

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            result = generate(tmp_project, model="gpt-4o", profile="tech")

        content = result.read_text()
        assert "```markdown" not in content
        assert "# Doc" in content

    def test_missing_prompt(self, tmp_path: Path):
        """#73 No prompt file → SystemExit(1)."""
        # Create minimal .tsu/config.json but no generate.md
        tsu_dir = tmp_path / ".tsu"
        tsu_dir.mkdir()
        (tsu_dir / "config.json").write_text(json.dumps({"model": "gpt-4o"}))

        MockClient = _make_mock_copilot()

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            with pytest.raises(SystemExit):
                generate(tmp_path, model="gpt-4o", profile="tech")

    def test_profile_uses_correct_prompt(self, tmp_project_with_profiles: Path):
        """#74 Profile 'ops' → loads generate-ops.md (not generate.md)."""
        MockClient = _make_mock_copilot("# Ops Doc\n\nOps content.")

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            result = generate(
                tmp_project_with_profiles, model="gpt-4o", profile="ops",
            )

        # Output should be at document-ops.md
        assert result.name == "document-ops.md"
        assert result.exists()


# ===================================================================
# Additional coverage tests
# ===================================================================


class TestListModelsObjectFormat:
    """Test list_models when SDK returns objects instead of strings."""

    def test_model_objects_with_id(self):
        """Models returned as objects with .id attribute."""

        class MockModel:
            def __init__(self, id):
                self.id = id

        class MockClient:
            def __init__(self, *a, **kw):
                pass
            async def start(self):
                pass
            async def stop(self):
                pass
            async def list_models(self):
                return [MockModel("gpt-4o"), MockModel("claude-sonnet-4.5")]

        with patch("tsu_cli.generator.CopilotClient", MockClient):
            with patch("tsu_cli.generator.Live"):
                from tsu_cli.generator import list_models
                result = list_models()
        assert "gpt-4o" in result
        assert "claude-sonnet-4.5" in result

    def test_model_objects_with_name(self):
        """Models returned as objects with .name but no .id."""

        class MockModel:
            def __init__(self, name):
                self.name = name

        class MockClient:
            def __init__(self, *a, **kw):
                pass
            async def start(self):
                pass
            async def stop(self):
                pass
            async def list_models(self):
                return [MockModel("model-a")]

        with patch("tsu_cli.generator.CopilotClient", MockClient):
            with patch("tsu_cli.generator.Live"):
                from tsu_cli.generator import list_models
                result = list_models()
        assert "model-a" in result


class TestListModelsException:
    """Test list_models when SDK raises an exception."""

    def test_sdk_error(self):
        """CopilotClient raises → returns empty list."""

        class MockClient:
            def __init__(self, *a, **kw):
                pass
            async def start(self):
                pass
            async def stop(self):
                pass
            async def list_models(self):
                raise RuntimeError("SDK not available")

        with patch("tsu_cli.generator.CopilotClient", MockClient):
            with patch("tsu_cli.generator.Live"):
                from tsu_cli.generator import list_models
                result = list_models()
        assert result == []


class TestGenerateNoResponse:
    """Test generate when Copilot returns no response."""

    def test_no_response_exits(self, tmp_project: Path):
        """Empty assistant response → SystemExit(1)."""

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
                    # Send idle without any assistant.message
                    self._on_cb(MockEvent("session.idle"))
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass

        class MockClient:
            def __init__(self, *a, **kw):
                pass
            async def start(self):
                pass
            async def stop(self):
                pass
            async def create_session(self, config):
                return MockSession()

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            with pytest.raises(SystemExit):
                generate(tmp_project, model="gpt-4o", profile="tech")


class TestGenerateStripsMdFences:
    """Test generate strips ```md fences."""

    def test_strips_md_fence(self, tmp_project: Path):
        """Response wrapped in ```md → fences stripped."""
        raw = "```md\n# Doc\nContent\n```"
        MockClient = _make_mock_copilot(raw)

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            result = generate(tmp_project, model="gpt-4o", profile="tech")

        content = result.read_text()
        assert "```md" not in content
        assert "# Doc" in content

    def test_strips_plain_fence(self, tmp_project: Path):
        """Response wrapped in plain ``` → fences stripped."""
        raw = "```\n# Doc\nContent\n```"
        MockClient = _make_mock_copilot(raw)

        with (
            patch("tsu_cli.generator.CopilotClient", MockClient),
            patch("tsu_cli.generator.PermissionHandler"),
            patch("tsu_cli.generator.Live"),
            patch("tsu_cli.generator.console"),
        ):
            from tsu_cli.generator import generate
            result = generate(tmp_project, model="gpt-4o", profile="tech")

        content = result.read_text()
        assert not content.startswith("```")
        assert "# Doc" in content
