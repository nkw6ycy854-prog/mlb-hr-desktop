from pathlib import Path
from types import SimpleNamespace

import mlb_hr
import mlb_hr.selftest as selftest


def test_runtime_statcast_status_reports_real_runtime_data(monkeypatch, tmp_path):
    parquet = tmp_path / "season=2025" / "month=07" / "statcast_2025-07-01.parquet"
    parquet.parent.mkdir(parents=True)
    parquet.write_bytes(b"placeholder")
    monkeypatch.setattr(
        selftest,
        "resolve_app_paths",
        lambda: SimpleNamespace(parquet_dir=tmp_path),
        raising=False,
    )

    status = selftest.runtime_statcast_status()

    assert status["available"] is True
    assert status["parquet_count"] == 1
    assert status["parquet_dir"] == str(tmp_path)


def test_run_self_test_exposes_ui_import_and_runtime_paths():
    result = selftest.run_self_test()

    assert "ui_import" in result["checks"]
    assert result["checks"]["ui_import"] is True

    assert "runtime_paths" in result["details"]
    runtime_paths = result["details"]["runtime_paths"]
    for key in ("data_dir", "db_path", "parquet_dir", "model_dir"):
        assert key in runtime_paths

    assert "bundled_model_version" in result["details"]
    assert "bundled_model_hash" in result["details"]
    assert "runtime_statcast" in result["details"]
    assert result["checks"]["sqlite_migration"] is True


def test_run_self_test_exposes_app_version():
    result = selftest.run_self_test()

    assert result["details"]["app_version"] == mlb_hr.__version__
