from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import platform
import sys


APP_DIR_NAME = "MLB HR"


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
    """Deprecated compatibility hook.

    Runtime paths intentionally no longer depend on QStandardPaths because its output
    changes with QCoreApplication organization/application identity. Keeping this
    function avoids breaking old imports/tests while resolve_app_paths stays stable in
    CLI, source, and packaged GUI contexts.
    """
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
        return (
            home / "Library" / "Application Support" / APP_DIR_NAME,
            home / "Library" / "Caches" / APP_DIR_NAME,
        )
    if system == "Windows":
        local = Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local"))
        return local / APP_DIR_NAME, local / APP_DIR_NAME / "Cache"
    xdg_data = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
    xdg_cache = Path(os.getenv("XDG_CACHE_HOME", home / ".cache"))
    return xdg_data / APP_DIR_NAME, xdg_cache / APP_DIR_NAME


def _has_statcast_data(path: Path) -> bool:
    return any(path.glob("season=*/month=*/statcast_*.parquet"))


def _legacy_statcast_dirs() -> list[Path]:
    """Known locations used by older/identity-less builds.

    The first entry on each platform is the accidental unscoped QStandardPaths
    location produced when resolve_app_paths() ran before QApplication identity was
    configured. The second is the original fallback directory used by this project.
    """
    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        base = home / "Library" / "Application Support"
        return [base / "statcast", base / "MLBHR" / "statcast"]
    if system == "Windows":
        local = Path(os.getenv("LOCALAPPDATA", home / "AppData" / "Local"))
        return [local / "statcast", local / "MLBHR" / "statcast"]
    xdg_data = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
    return [xdg_data / "statcast", xdg_data / "MLBHR" / "statcast"]


def _frozen_windows_bundled_statcast_dir() -> Path | None:
    """The Windows FULL release ships real Statcast parquet at
    <bundle_dir>/runtime_data/statcast, right next to app.exe (see
    scripts/windows_full_package.py). resolve_app_paths() previously never
    looked there -- only at %LOCALAPPDATA%\\MLB HR\\statcast -- so the
    distributed app.exe, run normally with no MLB_HR_DATA_DIR set, could
    never find its own bundled data (real bug, shipped in v1.2.0's Windows
    FULL asset; the release gate's self-test only passed because it
    injected MLB_HR_DATA_DIR as an override, which a real user never sets).

    Auto-discovers that location with zero environment variables and
    without ever copying the parquet files anywhere -- reads them in
    place. Only fires for a genuinely frozen Windows build (sys.frozen is
    set by both PyInstaller and Nuitka's standalone/onefile modes, which
    is what pyside6-deploy uses) with real data actually present; never on
    a source-mode run, never on another platform, never fabricated.
    """
    if platform.system() != "Windows":
        return None
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).parent / "runtime_data" / "statcast"
    return candidate if _has_statcast_data(candidate) else None


def _resolve_statcast_dir(canonical_data_dir: Path) -> Path:
    canonical = canonical_data_dir / "statcast"
    if _has_statcast_data(canonical):
        return canonical
    for candidate in _legacy_statcast_dirs():
        if candidate != canonical and _has_statcast_data(candidate):
            return candidate
    bundled = _frozen_windows_bundled_statcast_dir()
    if bundled is not None:
        return bundled
    return canonical


def resolve_app_paths() -> AppPaths:
    override = os.getenv("MLB_HR_DATA_DIR")
    if override:
        data = Path(override).expanduser().resolve()
        cache = data / "cache"
        parquet = data / "statcast"
    else:
        # Deliberately deterministic: do not depend on QApplication/QCoreApplication
        # identity. CLI diagnostics and the packaged GUI must resolve the same paths.
        data, cache = _fallback_paths()
        parquet = _resolve_statcast_dir(data)
    return AppPaths(
        data_dir=data,
        cache_dir=cache,
        log_dir=data / "logs",
        db_path=data / "app.db",
        parquet_dir=parquet,
        model_dir=data / "models",
    ).ensure()
