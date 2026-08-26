from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtCore import QThreadPool
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
    widget.density.setCurrentText("Compacta")
    widget.save()

    assert store.get_state("default_stake") == 25.0
    assert store.get_state("timezone_name") == "America/Santo_Domingo"
    assert store.get_state("ui_density") == "compact"
    assert "Guardado" in widget.feedback.text()


def test_current_timezone_value_remains_selectable():
    store = _FakeStore()
    store.set_state("timezone_name", "America/Santo_Domingo")
    widget = _widget(store)
    assert widget.timezone.currentText() == "America/Santo_Domingo"


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

    assert opened["path"] == str(tmp_path)


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
