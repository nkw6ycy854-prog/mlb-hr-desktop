"""V1.2.0 Centro de Estado -- "Ultimo settlement" persistence.

reconcile_pending() is the one method actually shared by all 3 real
trigger points (app.py's startup-after-health-OK and post-ACTUALIZAR
triggers call SettlementService(store).reconcile_pending() directly;
HistoryWidget's ACTUALIZAR RESULTADOS goes through SettlementCoordinator,
which also just calls this same method) -- so persisting the run summary
here, and only here, covers all three without duplicating logic.
"""
from __future__ import annotations

import pytest

from mlb_hr.services.settlement import SettlementService
from mlb_hr.storage.sqlite import SQLiteStore


@pytest.fixture()
def store(tmp_path):
    from mlb_hr.resources_runtime import packaged_migrations_dir
    with packaged_migrations_dir() as migrations_dir:
        s = SQLiteStore(tmp_path / "app.db", migrations_dir=migrations_dir)
        s.migrate()
    return s


def test_reconcile_pending_persists_a_last_settlement_run_summary(store):
    SettlementService(store).reconcile_pending()

    summary = store.get_state("last_settlement_run")
    assert summary is not None
    assert summary["checked"] == 0
    assert summary["updated"] == 0
    assert summary["errors"] == 0
    assert "at" in summary


def test_reconcile_pending_never_calls_analyze_slate(store, monkeypatch):
    # SettlementCoordinator's own contract already asserts this; re-confirm
    # it here since we're touching this exact method.
    import mlb_hr.services.analysis as analysis_module

    def _forbidden(*a, **k):
        raise AssertionError("reconcile_pending() must never call analyze_slate()")

    monkeypatch.setattr(analysis_module.AnalysisService, "analyze_slate", _forbidden, raising=True)

    SettlementService(store).reconcile_pending()  # must not raise
