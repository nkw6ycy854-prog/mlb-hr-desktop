from mlb_hr.services.health import HealthItem, HealthReport
from mlb_hr.services.status_center import build_status_center_report


class _FakeStore:
    def __init__(self, **state):
        self._state = state

    def get_state(self, key, default=None):
        return self._state.get(key, default)


def _health(model="OK", statcast="OK", database="OK", odds="OK"):
    return HealthReport(
        items=(
            HealthItem(key="model", label="Modelo", state=model, detail="V1.0.0"),
            HealthItem(key="statcast", label="Statcast", state=statcast, detail="1164 archivos"),
            HealthItem(key="database", label="Base de datos", state=database, detail="Conexión OK."),
            HealthItem(key="odds", label="Cuotas", state=odds, detail="Configurado."),
        ),
        critical_ok=(model == "OK" and statcast == "OK" and database == "OK"),
    )


def test_all_ok_and_nothing_checked_yet_is_not_sistema_ok():
    # Conservative rule: only ALL items OK counts as SISTEMA OK. Before any
    # MLB Feed/settlement/self-test check has ever run, those 3 show
    # "SIN COMPROBAR AUN", which is not OK -- so the global state must be
    # REQUIERE ATENCION, never a false SISTEMA OK on a cold start.
    report = build_status_center_report(_health(), _FakeStore())
    assert report.global_state == "REQUIERE ATENCION"
    mlb_feed = next(i for i in report.items if i.key == "mlb_feed")
    assert mlb_feed.state == "SIN COMPROBAR AUN"
    settlement = next(i for i in report.items if i.key == "last_settlement")
    assert settlement.state == "SIN COMPROBAR AUN"
    selftest = next(i for i in report.items if i.key == "selftest")
    assert selftest.state == "SIN COMPROBAR AUN"


def test_sistema_ok_only_when_every_item_is_ok():
    store = _FakeStore(
        last_mlb_feed_status={"quality": "GREEN", "messages": []},
        last_settlement_run={"checked": 3, "updated": 1, "errors": 0},
        last_selftest_passed=True,
    )
    report = build_status_center_report(_health(), store)
    assert all(i.state == "OK" for i in report.items)
    assert report.global_state == "SISTEMA OK"


def test_any_single_error_or_advertencia_forces_requiere_atencion():
    store = _FakeStore(
        last_mlb_feed_status={"quality": "GREEN", "messages": []},
        last_settlement_run={"checked": 3, "updated": 1, "errors": 0},
        last_selftest_passed=True,
    )
    report = build_status_center_report(_health(model="ERROR"), store)
    assert report.global_state == "REQUIERE ATENCION"


def test_selftest_is_binary_pass_ok_fail_error_never_a_fabricated_warning():
    store_pass = _FakeStore(last_selftest_passed=True)
    store_fail = _FakeStore(last_selftest_passed=False)
    r_pass = build_status_center_report(_health(), store_pass)
    r_fail = build_status_center_report(_health(), store_fail)
    assert next(i for i in r_pass.items if i.key == "selftest").state == "OK"
    assert next(i for i in r_fail.items if i.key == "selftest").state == "ERROR"


def test_mlb_feed_maps_slate_quality_severity_directly():
    for quality, expected in (("GREEN", "OK"), ("YELLOW", "ADVERTENCIA"), ("RED", "ERROR")):
        store = _FakeStore(last_mlb_feed_status={"quality": quality, "messages": []})
        report = build_status_center_report(_health(), store)
        assert next(i for i in report.items if i.key == "mlb_feed").state == expected


def test_last_settlement_shows_advertencia_when_errors_present():
    store = _FakeStore(last_settlement_run={"checked": 5, "updated": 2, "errors": 1})
    report = build_status_center_report(_health(), store)
    assert next(i for i in report.items if i.key == "last_settlement").state == "ADVERTENCIA"


def test_odds_not_configured_is_advertencia_not_error():
    report = build_status_center_report(_health(odds="NOT_CONFIGURED"), _FakeStore())
    assert next(i for i in report.items if i.key == "odds").state == "ADVERTENCIA"


def test_seven_components_present():
    report = build_status_center_report(_health(), _FakeStore())
    assert {i.key for i in report.items} == {
        "model", "statcast", "mlb_feed", "database", "odds", "last_settlement", "selftest",
    }
