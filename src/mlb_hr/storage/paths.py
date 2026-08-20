from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import platform


@dataclass(frozen=True, slots=True)
class AppPaths:
    data_dir: Path
    cache_dir: Path
    log_dir: Path
    db_path: Path
    parquet_dir: Path
    model_dir: Path

    def ensure(self) -> "AppPaths":
        for p in (self.data_dir, self.cache_dir, self.log_dir, self.parquet_dir, self.model_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self


def _qt_paths() -> tuple[Path, Path] | None:
    try:
        from PySide6.QtCore import QStandardPaths

        data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
        if data and cache:
            return Path(data), Path(cache)
    except Exception:
        return None
    return None


def _fallback_paths() -> tuple[Path, Path]:
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        return home / "Library" / "Application Support" / "MLBHR", home / "Library" / "Caches" / "MLBHR"
    if system == "Windows":
        local = Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local"))
        return local / "MLBHR", local / "MLBHR" / "Cache"
    xdg_data = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
    xdg_cache = Path(os.getenv("XDG_CACHE_HOME", home / ".cache"))
    return xdg_data / "MLBHR", xdg_cache / "MLBHR"


def resolve_app_paths() -> AppPaths:
    override = os.getenv("MLB_HR_DATA_DIR")
    if override:
        data = Path(override).expanduser().resolve()
        cache = data / "cache"
    else:
        paths = _qt_paths() or _fallback_paths()
        data, cache = paths
    return AppPaths(
        data_dir=data,
        cache_dir=cache,
        log_dir=data / "logs",
        db_path=data / "app.db",
        parquet_dir=data / "statcast",
        model_dir=data / "models",
    ).ensure()
