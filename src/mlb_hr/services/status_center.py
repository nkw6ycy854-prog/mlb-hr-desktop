from __future__ import annotations

from dataclasses import dataclass

from mlb_hr.services.health import HealthReport

_NOT_CHECKED = "SIN COMPROBAR AUN"


@dataclass(frozen=True)
class StatusItem:
    key: str
    label: str
    state: str  # OK | ADVERTENCIA | ERROR | SIN COMPROBAR AUN
    detail: str


@dataclass(frozen=True)
class StatusCenterReport:
    items: tuple[StatusItem, ...]
    global_state: str  # "SISTEMA OK" | "REQUIERE ATENCION"


def _health_item_state(state: str) -> str:
    if state == "OK":
        return "OK"
    if state == "ERROR":
        return "ERROR"
    return "ADVERTENCIA"  # NOT_CONFIGURED or any other real-but-non-OK state


_SLATE_QUALITY_STATE = {"GREEN": "OK", "YELLOW": "ADVERTENCIA", "RED": "ERROR"}


def build_status_center_report(health_report: HealthReport, store) -> StatusCenterReport:
    """Aggregates the 7 Centro de Estado components from real, already-
    produced signals only -- no new network calls, no fabricated states.
    """
    by_key = {i.key: i for i in health_report.items}
    items: list[StatusItem] = []

    for key, label in (("model", "Modelo"), ("statcast", "Statcast"), ("database", "Base de datos"), ("odds", "Odds API")):
        h = by_key.get(key)
        if h is None:
            items.append(StatusItem(key, label, "ADVERTENCIA", "Componente no evaluado."))
        else:
            items.append(StatusItem(key, label, _health_item_state(h.state), h.detail))

    feed_status = store.get_state("last_mlb_feed_status", None)
    if feed_status is None:
        items.append(StatusItem("mlb_feed", "MLB Feed", _NOT_CHECKED, "Aún no se ha ejecutado ACTUALIZAR en esta sesión."))
    else:
        quality = feed_status.get("quality", "")
        state = _SLATE_QUALITY_STATE.get(quality, "ADVERTENCIA")
        detail = "; ".join(feed_status.get("messages", [])) or f"Última actualización: calidad {quality}."
        items.append(StatusItem("mlb_feed", "MLB Feed", state, detail))

    settlement = store.get_state("last_settlement_run", None)
    if settlement is None:
        items.append(StatusItem("last_settlement", "Último settlement", _NOT_CHECKED, "Aún no se ha ejecutado ningún settlement en esta sesión."))
    else:
        errors = settlement.get("errors", 0)
        state = "ADVERTENCIA" if errors else "OK"
        detail = f"{settlement.get('checked', 0)} revisadas, {settlement.get('updated', 0)} actualizadas, {errors} error(es)."
        items.append(StatusItem("last_settlement", "Último settlement", state, detail))

    selftest_passed = store.get_state("last_selftest_passed", None)
    if selftest_passed is None:
        items.append(StatusItem("selftest", "SELF-TEST", _NOT_CHECKED, "Aún no se ha ejecutado el self-test en esta sesión."))
    else:
        items.append(StatusItem("selftest", "SELF-TEST", "OK" if selftest_passed else "ERROR", "PASS" if selftest_passed else "FAIL"))

    global_state = "SISTEMA OK" if all(i.state == "OK" for i in items) else "REQUIERE ATENCION"
    return StatusCenterReport(items=tuple(items), global_state=global_state)
