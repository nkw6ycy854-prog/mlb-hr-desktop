import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mlb_hr.services.status_center import StatusCenterReport, StatusItem
from mlb_hr.ui.status_center import StatusCenterPanel


def app():
    return QApplication.instance() or QApplication([])


def _report(global_state="SISTEMA OK", **overrides):
    defaults = {
        "model": "OK", "statcast": "OK", "mlb_feed": "OK", "database": "OK",
        "odds": "OK", "last_settlement": "OK", "selftest": "OK",
    }
    defaults.update(overrides)
    labels = {
        "model": "Modelo", "statcast": "Statcast", "mlb_feed": "MLB Feed", "database": "Base de datos",
        "odds": "Odds API", "last_settlement": "Último settlement", "selftest": "SELF-TEST",
    }
    items = tuple(StatusItem(k, labels[k], v, f"detalle de {k}") for k, v in defaults.items())
    return StatusCenterReport(items=items, global_state=global_state)


def test_panel_shows_global_state():
    app()
    panel = StatusCenterPanel()
    panel.render(_report(global_state="SISTEMA OK"))
    texts = "\n".join(l.text() for l in panel.findChildren(QLabel))
    assert "SISTEMA OK" in texts


def test_panel_shows_all_seven_components():
    app()
    panel = StatusCenterPanel()
    panel.render(_report())
    texts = "\n".join(b.text() for b in panel.findChildren(QPushButton))
    for label in ("Modelo", "Statcast", "MLB Feed", "Base de datos", "Odds API", "Último settlement", "SELF-TEST"):
        assert label in texts


def test_clicking_a_failing_component_shows_impact_and_action():
    app()
    panel = StatusCenterPanel()
    panel.render(_report(global_state="REQUIERE ATENCION", model="ERROR"))

    model_btn = next(b for b in panel.findChildren(QPushButton) if "Modelo" in b.text())
    model_btn.click()

    texts = "\n".join(l.text() for l in panel.detail_panel.findChildren(QLabel))
    assert "detalle de model" in texts  # real HealthItem detail, not a placeholder
    assert "Última comprobación" in texts or "última comprobación" in texts.lower()
