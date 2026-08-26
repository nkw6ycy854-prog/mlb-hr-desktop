from types import SimpleNamespace

from mlb_hr.services.health import HealthService


def _package(*, release_ready=True, model_version="V1.0.0"):
    return SimpleNamespace(release_ready=release_ready, manifest=SimpleNamespace(model_version=model_version))


def _service(*, release_ready=True, model_version="V1.0.0", has_statcast=True, odds=SimpleNamespace()):
    return SimpleNamespace(
        package=_package(release_ready=release_ready, model_version=model_version),
        analytics=SimpleNamespace(has_data=lambda: has_statcast),
        odds=odds,
    )


class _StubStore:
    def __init__(self, healthy=True):
        self._healthy = healthy

    def healthcheck(self):
        return self._healthy


def test_missing_statcast_is_error_and_not_critical_ok():
    service = _service(has_statcast=False)
    report = HealthService(service, paths=None, store=_StubStore()).run()

    statcast_item = next(i for i in report.items if i.key == "statcast")
    assert statcast_item.state == "ERROR"
    assert report.critical_ok is False


def test_release_ready_model_statcast_and_db_are_ok():
    service = _service(has_statcast=True)
    report = HealthService(service, paths=None, store=_StubStore(healthy=True)).run()

    for key in ("model", "statcast", "database"):
        item = next(i for i in report.items if i.key == key)
        assert item.state == "OK", f"{key} expected OK, got {item.state}"
    assert report.critical_ok is True


def test_no_odds_provider_is_not_configured_and_not_critical():
    service = _service(odds=None)
    report = HealthService(service, paths=None, store=_StubStore()).run()

    odds_item = next(i for i in report.items if i.key == "odds")
    assert odds_item.state == "NOT_CONFIGURED"
    assert report.critical_ok is True


def test_db_healthcheck_failure_is_error_and_not_critical_ok():
    service = _service()
    report = HealthService(service, paths=None, store=_StubStore(healthy=False)).run()

    db_item = next(i for i in report.items if i.key == "database")
    assert db_item.state == "ERROR"
    assert report.critical_ok is False


def test_unvalidated_model_is_error():
    service = _service(release_ready=False)
    report = HealthService(service, paths=None, store=_StubStore()).run()

    model_item = next(i for i in report.items if i.key == "model")
    assert model_item.state == "ERROR"
    assert report.critical_ok is False


def test_model_item_detail_always_reports_the_actual_loaded_version():
    service = _service(model_version="V0.9.0", release_ready=True)
    report = HealthService(service, paths=None, store=_StubStore()).run()

    model_item = next(i for i in report.items if i.key == "model")
    assert model_item.state == "ERROR"
    assert "V0.9.0" in model_item.detail


def test_statcast_ok_detail_includes_real_parquet_file_count(tmp_path):
    season_dir = tmp_path / "season=2026" / "month=04"
    season_dir.mkdir(parents=True)
    (season_dir / "statcast_2026-04-01.parquet").write_text("x")
    (season_dir / "statcast_2026-04-02.parquet").write_text("x")
    paths = SimpleNamespace(parquet_dir=tmp_path)
    service = _service(has_statcast=True)

    report = HealthService(service, paths=paths, store=_StubStore()).run()

    statcast_item = next(i for i in report.items if i.key == "statcast")
    assert statcast_item.state == "OK"
    assert "2" in statcast_item.detail


def test_statcast_detail_never_fabricates_a_count_without_paths():
    service = _service(has_statcast=True)
    report = HealthService(service, paths=None, store=_StubStore()).run()

    statcast_item = next(i for i in report.items if i.key == "statcast")
    assert statcast_item.state == "OK"
    assert not any(ch.isdigit() for ch in statcast_item.detail)
