from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtCore import QThreadPool, QUrl
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.ai.providers import AIReview
from mlb_hr.domain.models import ProviderMeta
from mlb_hr.providers.base import ProviderResult
from mlb_hr.ui.settings import SettingsWidget


def _pump(timeout_ms=2000):
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    QTest.qWait(50)


def app():
    return QApplication.instance() or QApplication([])


class _FakeStore:
    def __init__(self):
        self._state = {}

    def get_state(self, key, default=None):
        return self._state.get(key, default)

    def set_state(self, key, value):
        self._state[key] = value


def _widget(store=None) -> SettingsWidget:
    app()
    return SettingsWidget(store or _FakeStore())


def _widget_texts(widget) -> str:
    return "\n".join(label.text() for label in widget.findChildren(QLabel))


def test_settings_has_four_section_titles():
    widget = _widget()
    texts = {label.text() for label in widget.findChildren(QLabel)}
    for title in ("GENERAL", "CUOTAS", "IA", "SISTEMA"):
        assert title in texts


def test_saving_general_section_persists_and_gives_feedback():
    store = _FakeStore()
    widget = _widget(store)

    widget.stake.setCurrentText("$25")
    widget.timezone.setCurrentText("America/Santo_Domingo")
    widget.save()

    assert store.get_state("default_stake") == 25.0
    assert store.get_state("timezone_name") == "America/Santo_Domingo"
    assert "Guardado" in widget.feedback.text()


def test_density_control_was_removed_it_never_affected_anything():
    # ui_density was persisted and shown as "changed" on save, but nothing in
    # src/ ever read it back -- a purely cosmetic control per the audit's own
    # rule (functional or removed). Confirms it's gone, not just hidden.
    widget = _widget()
    assert not hasattr(widget, "density")
    assert "Densidad" not in _widget_texts(widget)


def test_changing_stake_tells_the_user_a_restart_is_needed():
    # AnalysisService.stake is fixed at construction (build_services() reads
    # default_stake once); a change here only affects the NEXT app launch, so
    # the feedback must say so, matching how AI/API key changes already do.
    store = _FakeStore()
    widget = _widget(store)

    widget.stake.setCurrentText("$25")
    widget.save()

    assert "reinicia" in widget.feedback.text().lower()


def test_current_timezone_value_remains_selectable():
    store = _FakeStore()
    store.set_state("timezone_name", "America/Santo_Domingo")
    widget = _widget(store)
    assert widget.timezone.currentText() == "America/Santo_Domingo"


def test_stake_combo_has_minimum_width_to_avoid_clipping():
    widget = _widget()
    assert widget.stake.minimumWidth() >= 120


def test_timezone_combo_popup_is_bounded_and_scrollable():
    widget = _widget()
    assert 0 < widget.timezone.maxVisibleItems() <= 15


def test_stake_combo_includes_personalizada_option():
    widget = _widget()
    items = [widget.stake.itemText(i) for i in range(widget.stake.count())]
    assert "Personalizada…" in items


def test_custom_stake_spinbox_hidden_by_default_for_predefined_stake():
    store = _FakeStore()
    store.set_state("default_stake", 25.0)
    widget = _widget(store)
    assert widget.stake.currentText() == "$25"
    assert widget.stake_custom.isHidden() is True


def test_selecting_personalizada_shows_custom_stake_spinbox():
    widget = _widget()
    widget.stake.setCurrentText("Personalizada…")
    assert widget.stake_custom.isHidden() is False


def test_saving_custom_stake_persists_and_reloads_on_reopen():
    store = _FakeStore()
    widget = _widget(store)
    widget.stake.setCurrentText("Personalizada…")
    widget.stake_custom.setValue(37.5)
    widget.save()

    assert store.get_state("default_stake") == 37.5

    widget2 = _widget(store)
    assert widget2.stake.currentText() == "Personalizada…"
    assert widget2.stake_custom.value() == 37.5
    assert widget2.stake_custom.isHidden() is False


def test_api_keys_are_masked():
    widget = _widget()
    assert widget.odds_key.echoMode() == widget.odds_key.EchoMode.Password


def _meta():
    return ProviderMeta(provider="TEST", fetched_at=datetime.now(timezone.utc))


def test_probar_conexion_disables_button_then_shows_ok():
    widget = _widget()

    class _FakeOddsProvider:
        def test_connection(self):
            return ProviderResult(True, _meta())

    widget.odds_provider_factory = lambda api_key: _FakeOddsProvider()
    widget.test_connection_btn.click()
    assert widget.test_connection_btn.isEnabled() is False
    _pump()

    assert widget.test_connection_btn.isEnabled() is True
    assert "OK" in widget.odds_feedback.text()


def test_probar_conexion_shows_structured_error_message():
    widget = _widget()

    class _FailingOddsProvider:
        def test_connection(self):
            return ProviderResult(False, _meta(), error_code="ODDS_UNAVAILABLE", error_message="boom")

    widget.odds_provider_factory = lambda api_key: _FailingOddsProvider()
    widget.test_connection_btn.click()
    _pump()

    assert "boom" in widget.odds_feedback.text()


def test_probar_ia_shows_provider_and_model_on_success():
    widget = _widget()

    class _FakeAIProvider:
        def review(self, role, payload):
            return AIReview(True, "groq", "llama-3", role, "PASS", [])

    widget.ai_provider.setCurrentText("Groq")
    widget.groq_model.setText("llama-3")
    widget.ai_provider_builder = lambda code, key, model: _FakeAIProvider()
    widget.test_ai_btn.click()
    assert widget.test_ai_btn.isEnabled() is False
    _pump()

    assert widget.test_ai_btn.isEnabled() is True
    assert "groq" in widget.ai_feedback.text()
    assert "llama-3" in widget.ai_feedback.text()


def test_probar_ia_shows_error_when_provider_unavailable():
    widget = _widget()

    class _FailingAIProvider:
        def review(self, role, payload):
            return AIReview(False, "groq", "llama-3", role, error="clave inválida")

    widget.ai_provider.setCurrentText("Groq")
    widget.groq_model.setText("llama-3")
    widget.ai_provider_builder = lambda code, key, model: _FailingAIProvider()
    widget.test_ai_btn.click()
    _pump()

    assert "clave inválida" in widget.ai_feedback.text()


def test_abrir_carpeta_de_datos_opens_real_runtime_path(tmp_path):
    opened = {}
    paths = SimpleNamespace(data_dir=tmp_path)
    widget = SettingsWidget(_FakeStore(), paths=paths, open_url_func=lambda url: opened.setdefault("path", url.toLocalFile()))

    widget.open_data_folder_btn.click()

    # QUrl.toLocalFile() always normalizes to forward slashes, even on Windows,
    # while str(tmp_path) uses native OS separators -- round-trip the expected
    # side through the same QUrl normalization so this assertion is
    # platform-independent, matching what _open_data_folder() itself does.
    assert opened["path"] == QUrl.fromLocalFile(str(tmp_path)).toLocalFile()


def test_ejecutar_selftest_shows_pass_and_records_timestamp():
    store = _FakeStore()
    widget = _widget(store)
    widget.self_test_runner = lambda **kwargs: {"passed": True, "checks": {"a": True}, "details": {}}

    widget.run_selftest_btn.click()
    assert widget.run_selftest_btn.isEnabled() is False
    _pump()

    assert widget.run_selftest_btn.isEnabled() is True
    assert "PASS" in widget.selftest_feedback.text()
    assert store.get_state("last_selftest_at") is not None


def test_ejecutar_selftest_shows_fail_with_failed_check_names():
    widget = _widget()
    widget.self_test_runner = lambda **kwargs: {"passed": False, "checks": {"a": True, "b": False}, "details": {}}

    widget.run_selftest_btn.click()
    _pump()

    assert "FAIL" in widget.selftest_feedback.text()
    assert "b" in widget.selftest_feedback.text()


def _health_item(key, label, state, detail):
    from mlb_hr.services.health import HealthItem
    return HealthItem(key=key, label=label, state=state, detail=detail)


def _health_report(*, model_ok=True, statcast_ok=True, db_ok=True):
    from mlb_hr.services.health import HealthReport
    items = (
        _health_item("model", "Modelo", "OK" if model_ok else "ERROR",
                     "V1.0.0" if model_ok else "V0.9.0 (esperado V1.0.0, release_ready=False)"),
        _health_item("statcast", "Statcast", "OK" if statcast_ok else "ERROR",
                     "Datos disponibles (3 archivo(s))." if statcast_ok else "Statcast no fue encontrado."),
        _health_item("database", "Base de datos", "OK" if db_ok else "ERROR",
                     "Conexión OK." if db_ok else "No se pudo conectar a la base de datos local."),
        _health_item("odds", "Cuotas", "NOT_CONFIGURED", "SIN API / NO CONFIGURADO."),
    )
    return HealthReport(items=items, critical_ok=model_ok and statcast_ok and db_ok)


def test_sistema_shows_not_run_before_any_selftest():
    widget = _widget()
    assert "NO EJECUTADO" in widget.last_selftest.text()


def test_apply_health_report_updates_sistema_labels_with_ok_states():
    widget = _widget()

    widget.apply_health_report(_health_report(model_ok=True, statcast_ok=True, db_ok=True))

    assert "V1.0.0" in widget.model_status.text()
    assert "OK" in widget.model_status.text()
    assert "OK" in widget.statcast_status.text()
    assert widget.db_status.text() == "● OK"


def test_apply_health_report_updates_sistema_labels_with_error_states():
    widget = _widget()

    widget.apply_health_report(_health_report(model_ok=False, statcast_ok=False, db_ok=False))

    assert "ERROR" in widget.model_status.text()
    assert "V0.9.0" in widget.model_status.text()
    assert "ERROR" in widget.statcast_status.text()
    assert widget.db_status.text() == "● ERROR"


def test_ejecutar_selftest_updates_sistema_last_selftest_label_immediately():
    widget = _widget()
    widget.self_test_runner = lambda **kwargs: {"passed": True, "checks": {"a": True}, "details": {}}

    widget.run_selftest_btn.click()
    _pump()

    assert "PASS" in widget.last_selftest.text()
    assert "NO EJECUTADO" not in widget.last_selftest.text()


def test_ejecutar_selftest_fail_updates_sistema_last_selftest_label():
    widget = _widget()
    widget.self_test_runner = lambda **kwargs: {"passed": False, "checks": {"a": False}, "details": {}}

    widget.run_selftest_btn.click()
    _pump()

    assert "FAIL" in widget.last_selftest.text()


def test_selftest_label_uses_configured_timezone_not_os_local():
    store = _FakeStore()
    store.set_state("timezone_name", "America/Santo_Domingo")
    widget = _widget(store)
    iso_text = datetime(2026, 8, 26, 23, 15, tzinfo=timezone.utc).isoformat()

    assert widget._selftest_label(True, iso_text) == "● PASS · 7:15 PM"
