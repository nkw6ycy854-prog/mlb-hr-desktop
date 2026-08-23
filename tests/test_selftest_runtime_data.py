from pathlib import Path
from types import SimpleNamespace

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
