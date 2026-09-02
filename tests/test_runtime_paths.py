from pathlib import Path

import mlb_hr.storage.paths as paths


def _fake_mac(monkeypatch, home: Path) -> None:
    monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: home)


def _fake_windows(monkeypatch, home: Path, *, localappdata: Path | None = None) -> None:
    monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.platform, "system", lambda: "Windows")
    monkeypatch.setattr(paths.Path, "home", lambda: home)
    if localappdata is not None:
        monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    else:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)


def test_runtime_paths_do_not_depend_on_qt_application_identity(monkeypatch, tmp_path):
    _fake_mac(monkeypatch, tmp_path)
    wrong_data = tmp_path / "qt-identity-dependent-data"
    wrong_cache = tmp_path / "qt-identity-dependent-cache"
    monkeypatch.setattr(paths, "_qt_paths", lambda: (wrong_data, wrong_cache))

    resolved = paths.resolve_app_paths()

    assert resolved.data_dir == tmp_path / "Library" / "Application Support" / "MLB HR"
    assert resolved.cache_dir == tmp_path / "Library" / "Caches" / "MLB HR"


def test_runtime_reuses_unscoped_legacy_statcast_when_canonical_is_empty(monkeypatch, tmp_path):
    _fake_mac(monkeypatch, tmp_path)
    monkeypatch.setattr(paths, "_qt_paths", lambda: None)
    legacy = tmp_path / "Library" / "Application Support" / "statcast"
    parquet = legacy / "season=2024" / "month=04" / "statcast_2024-04-01.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"parquet-placeholder")

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir == legacy


# --- Windows FULL release: bundled runtime_data/statcast auto-discovery ---
#
# Root cause of the real-world bug: the Windows FULL package ships parquet at
# <bundle_dir>/runtime_data/statcast, next to app.exe. resolve_app_paths()
# only ever looked at %LOCALAPPDATA%\MLB HR\statcast (plus legacy dirs), so
# the distributed app.exe -- run normally, no MLB_HR_DATA_DIR set -- could
# never find its own bundled data. The self-test that shipped with v1.2.0
# only passed because windows_full_package.py's gate injected
# MLB_HR_DATA_DIR as an env override, which a real end user never sets.

def test_frozen_windows_build_auto_discovers_bundled_statcast_next_to_executable(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _fake_windows(monkeypatch, home, localappdata=tmp_path / "AppData" / "Local")
    bundle_dir = tmp_path / "bundle"
    exe_path = bundle_dir / "app.exe"
    bundle_dir.mkdir(parents=True)
    parquet = bundle_dir / "runtime_data" / "statcast" / "season=2024" / "month=04" / "statcast_2024-04-01.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"parquet-placeholder")
    monkeypatch.setattr(paths.sys, "executable", str(exe_path))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir == bundle_dir / "runtime_data" / "statcast"


def test_frozen_windows_build_keeps_data_db_cache_logs_in_normal_user_locations(monkeypatch, tmp_path):
    # The fix must ONLY affect parquet_dir -- data/db/cache/logs must stay
    # writable in the normal per-user location, never redirected into the
    # (likely read-only, Program-Files-style) install directory.
    home = tmp_path / "home"
    localappdata = tmp_path / "AppData" / "Local"
    _fake_windows(monkeypatch, home, localappdata=localappdata)
    bundle_dir = tmp_path / "bundle"
    exe_path = bundle_dir / "app.exe"
    bundle_dir.mkdir(parents=True)
    parquet = bundle_dir / "runtime_data" / "statcast" / "season=2024" / "month=04" / "statcast_2024-04-01.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"parquet-placeholder")
    monkeypatch.setattr(paths.sys, "executable", str(exe_path))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)

    resolved = paths.resolve_app_paths()

    assert resolved.data_dir == localappdata / "MLB HR"
    assert resolved.db_path == localappdata / "MLB HR" / "app.db"
    assert resolved.cache_dir == localappdata / "MLB HR" / "Cache"
    assert resolved.log_dir == localappdata / "MLB HR" / "logs"


def test_mlb_hr_data_dir_override_still_wins_over_the_bundled_directory(monkeypatch, tmp_path):
    home = tmp_path / "home"
    _fake_windows(monkeypatch, home, localappdata=tmp_path / "AppData" / "Local")
    bundle_dir = tmp_path / "bundle"
    exe_path = bundle_dir / "app.exe"
    bundle_dir.mkdir(parents=True)
    parquet = bundle_dir / "runtime_data" / "statcast" / "season=2024" / "month=04" / "statcast_x.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"placeholder")
    monkeypatch.setattr(paths.sys, "executable", str(exe_path))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    override = tmp_path / "explicit-override"
    monkeypatch.setenv("MLB_HR_DATA_DIR", str(override))

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir == override / "statcast"
    assert resolved.data_dir == override


def test_frozen_windows_build_without_bundled_data_falls_back_to_localappdata(monkeypatch, tmp_path):
    # A frozen Windows build with no runtime_data/statcast next to app.exe
    # (e.g. the bare, non-FULL package) must not fabricate a location --
    # falls back to the normal canonical (possibly empty) directory.
    home = tmp_path / "home"
    localappdata = tmp_path / "AppData" / "Local"
    _fake_windows(monkeypatch, home, localappdata=localappdata)
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    monkeypatch.setattr(paths.sys, "executable", str(bundle_dir / "app.exe"))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir == localappdata / "MLB HR" / "statcast"


def test_source_mode_windows_run_never_looks_next_to_the_python_interpreter(monkeypatch, tmp_path):
    # sys.frozen is unset for a normal `python -m mlb_hr...` run -- the
    # auto-discovery must never fire and treat the Python interpreter's own
    # directory as if it were a shipped bundle.
    home = tmp_path / "home"
    localappdata = tmp_path / "AppData" / "Local"
    _fake_windows(monkeypatch, home, localappdata=localappdata)
    interpreter_dir = tmp_path / "python-install"
    parquet = interpreter_dir / "runtime_data" / "statcast" / "season=2024" / "month=04" / "statcast_x.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"placeholder")
    monkeypatch.setattr(paths.sys, "executable", str(interpreter_dir / "python.exe"))
    monkeypatch.delattr(paths.sys, "frozen", raising=False)

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir == localappdata / "MLB HR" / "statcast"


def test_frozen_bundled_statcast_is_never_auto_discovered_on_macos(monkeypatch, tmp_path):
    # Explicit platform scope per the approved fix -- macOS's own
    # distribution model doesn't bundle Statcast into the .app, and this
    # auto-discovery must stay Windows-only.
    home = tmp_path / "home"
    _fake_mac(monkeypatch, home)
    monkeypatch.setattr(paths, "_qt_paths", lambda: None)
    bundle_dir = tmp_path / "MLB HR.app" / "Contents" / "MacOS"
    parquet = bundle_dir / "runtime_data" / "statcast" / "season=2024" / "month=04" / "statcast_x.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"placeholder")
    monkeypatch.setattr(paths.sys, "executable", str(bundle_dir / "app"))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)

    resolved = paths.resolve_app_paths()

    assert resolved.parquet_dir != bundle_dir / "runtime_data" / "statcast"
