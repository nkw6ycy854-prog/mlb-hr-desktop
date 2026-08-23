from pathlib import Path

import mlb_hr.storage.paths as paths


def _fake_mac(monkeypatch, home: Path) -> None:
    monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: home)


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
