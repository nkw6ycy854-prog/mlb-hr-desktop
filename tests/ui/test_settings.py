from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.ui.settings import SettingsWidget


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
