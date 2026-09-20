from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIRECTORY_NAME = "StreamingFinder"


def is_frozen() -> bool:
    """Return True when running from a PyInstaller-built executable."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Return the repository root when running from source."""
    return Path(__file__).resolve().parents[2]


def user_data_dir() -> Path:
    """Return the per-user writable directory used by the packaged app."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIRECTORY_NAME

    # Fallback keeps non-Windows development/test environments predictable.
    return Path.home() / ".streamingfinder"


def runtime_data_dir() -> Path:
    """Return the directory containing writable runtime state."""
    if is_frozen():
        return user_data_dir()
    return project_root() / "data"


def default_database_path() -> Path:
    if is_frozen():
        return runtime_data_dir() / "streaming_finder.db"
    return runtime_data_dir() / "streaming_finder.db"


def settings_env_path() -> Path:
    """Return the .env path appropriate for source or packaged execution."""
    if is_frozen():
        return user_data_dir() / ".env"
    return project_root() / ".env"


def bundled_resource_path(*parts: str) -> Path:
    """Resolve a read-only resource bundled by PyInstaller or present in source."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).joinpath(*parts)
    return project_root().joinpath(*parts)
