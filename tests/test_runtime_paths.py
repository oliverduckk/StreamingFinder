from pathlib import Path

from app.core import paths
from app.core.config import Settings


def test_source_runtime_paths_are_project_local(monkeypatch) -> None:
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    assert paths.runtime_data_dir() == paths.project_root() / "data"
    assert paths.default_database_path() == paths.project_root() / "data" / "streaming_finder.db"
    assert paths.settings_env_path() == paths.project_root() / ".env"


def test_packaged_runtime_paths_use_local_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert paths.runtime_data_dir() == tmp_path / "StreamingFinder"
    assert paths.default_database_path() == tmp_path / "StreamingFinder" / "streaming_finder.db"
    assert paths.settings_env_path() == tmp_path / "StreamingFinder" / ".env"


def test_settings_can_still_override_database_path(tmp_path: Path) -> None:
    custom_database = tmp_path / "custom.db"
    settings = Settings(database_path=str(custom_database))
    assert settings.database_path == str(custom_database)
