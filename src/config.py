"""Configuration management for tsu-cli.

Handles reading and writing .tsu/config.json and .tsu/confluence.json.
Supports profile-based multi-document generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TSU_DIR = ".tsu"
CONFIG_FILE = "config.json"
CONFLUENCE_FILE = "confluence.json"
DOCUMENT_FILE = "document.md"
PROMPT_FILE = "generate.md"
DEFAULT_PROFILE = "tech"

DEFAULT_CONFIG: dict[str, Any] = {
    "model": "gpt-4o",
}

DEFAULT_CONFLUENCE: dict[str, Any] = {
    "parent_page_url": "",
    "page_title": "",
    "page_id": None,
}


def get_tsu_dir(project_dir: Path | None = None) -> Path:
    """Return the .tsu directory path for the given project (defaults to cwd)."""
    base = project_dir or Path.cwd()
    return base / TSU_DIR


def validate_write_path(target: Path, project_dir: Path | None = None) -> Path:
    """Ensure *target* resolves inside the ``.tsu/`` directory.

    Returns the resolved absolute path on success.
    Raises :class:`ValueError` if the path escapes ``.tsu/``.
    """
    base = project_dir or Path.cwd()
    tsu_abs = (base / TSU_DIR).resolve()
    target_abs = target.resolve()
    if not target_abs.is_relative_to(tsu_abs):
        raise ValueError(
            f"Write blocked: {target} resolves outside .tsu/ directory "
            f"({target_abs} is not inside {tsu_abs})"
        )
    return target_abs


def safe_write_text(
    path: Path, content: str, project_dir: Path | None = None
) -> None:
    """Write *content* to *path* after verifying it is inside ``.tsu/``."""
    validate_write_path(path, project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def ensure_tsu_dir(project_dir: Path | None = None) -> Path:
    """Create .tsu directory if it doesn't exist and return its path."""
    tsu_dir = get_tsu_dir(project_dir)
    tsu_dir.mkdir(parents=True, exist_ok=True)
    return tsu_dir


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file and return its contents as a dict."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(
    path: Path, data: dict[str, Any], project_dir: Path | None = None
) -> None:
    """Write a dict to a JSON file with pretty formatting.

    Validates that *path* is inside ``.tsu/`` before writing.
    """
    validate_write_path(path, project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_config(project_dir: Path | None = None) -> dict[str, Any]:
    """Read .tsu/config.json, returning defaults if file doesn't exist."""
    tsu_dir = get_tsu_dir(project_dir)
    config = {**DEFAULT_CONFIG, **_read_json(tsu_dir / CONFIG_FILE)}
    return config


def write_config(data: dict[str, Any], project_dir: Path | None = None) -> Path:
    """Write .tsu/config.json and return the file path."""
    tsu_dir = ensure_tsu_dir(project_dir)
    path = tsu_dir / CONFIG_FILE
    _write_json(path, data, project_dir)
    return path


def _confluence_filename(profile: str) -> str:
    """Return the confluence config filename for a profile.

    The 'tech' profile uses the legacy name 'confluence.json' for
    backward compatibility.  Other profiles use 'confluence-{profile}.json'.
    """
    if profile == DEFAULT_PROFILE:
        return CONFLUENCE_FILE
    return f"confluence-{profile}.json"


def _prompt_filename(profile: str) -> str:
    """Return the prompt template filename for a profile.

    The 'tech' profile uses 'generate.md'.  Others use 'generate-{profile}.md'.
    """
    if profile == DEFAULT_PROFILE:
        return PROMPT_FILE
    return f"generate-{profile}.md"


def _document_filename(profile: str) -> str:
    """Return the output document filename for a profile.

    The 'tech' profile uses 'document.md'.  Others use 'document-{profile}.md'.
    """
    if profile == DEFAULT_PROFILE:
        return DOCUMENT_FILE
    return f"document-{profile}.md"


def read_confluence(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Read the confluence config for *profile*, returning defaults if missing."""
    tsu_dir = get_tsu_dir(project_dir)
    filename = _confluence_filename(profile)
    config = {**DEFAULT_CONFLUENCE, **_read_json(tsu_dir / filename)}
    return config


def write_confluence(
    data: dict[str, Any],
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Write the confluence config for *profile* and return the file path."""
    tsu_dir = ensure_tsu_dir(project_dir)
    path = tsu_dir / _confluence_filename(profile)
    _write_json(path, data, project_dir)
    return path


def get_document_path(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Return the output document path for *profile*."""
    tsu_dir = get_tsu_dir(project_dir)
    return tsu_dir / _document_filename(profile)


def get_prompt_path(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Return the prompt template path for *profile*."""
    return get_tsu_dir(project_dir) / _prompt_filename(profile)


def seed_prompt(
    project_dir: Path | None = None,
    profile: str = DEFAULT_PROFILE,
) -> Path:
    """Copy the built-in generate.md into .tsu/ for *profile* if it doesn't already exist.

    All profiles are seeded from the same built-in ``generate.md``.
    For the 'tech' profile the prompt works as-is.  For custom profiles the
    user edits the seeded copy to fit their document type.

    Returns the path to the seeded prompt file.
    """
    from importlib import resources

    tsu_dir = ensure_tsu_dir(project_dir)
    prompt_path = tsu_dir / _prompt_filename(profile)
    if not prompt_path.exists():
        builtin = resources.files("tsu_cli.prompts") / PROMPT_FILE
        safe_write_text(prompt_path, builtin.read_text(encoding="utf-8"), project_dir)
    return prompt_path


def list_profiles(project_dir: Path | None = None) -> list[str]:
    """Return a sorted list of profile names found in .tsu/.

    Profiles are discovered by scanning for ``generate*.md`` files.
    """
    tsu_dir = get_tsu_dir(project_dir)
    if not tsu_dir.exists():
        return []
    profiles: list[str] = []
    for path in tsu_dir.glob("generate*.md"):
        name = path.stem  # e.g. 'generate' or 'generate-func'
        if name == "generate":
            profiles.append(DEFAULT_PROFILE)
        elif name.startswith("generate-"):
            profiles.append(name[len("generate-"):])
    return sorted(profiles)


def is_initialized(project_dir: Path | None = None) -> bool:
    """Check if the .tsu directory has been initialized."""
    tsu_dir = get_tsu_dir(project_dir)
    return (tsu_dir / CONFIG_FILE).exists()
