from __future__ import annotations

from dataclasses import dataclass

MODEL_VERSION = "V1.0.0"


@dataclass(frozen=True)
class HealthItem:
    key: str
    label: str
    state: str  # OK | WARNING | ERROR | NOT_CONFIGURED
    detail: str


@dataclass(frozen=True)
class HealthReport:
    items: tuple[HealthItem, ...]
    critical_ok: bool


class HealthService:
    """Lightweight, deterministic startup health check.

    Deliberately performs no MLB network call: provider availability is
    refreshed by the existing first ACTUALIZAR, keeping startup fast and
    independent of external service latency.
    """

    _CRITICAL_KEYS = ("model", "statcast", "database")

    def __init__(self, service, paths, store) -> None:
        self.service = service
        self.paths = paths
        self.store = store

    def run(self) -> HealthReport:
        items = [
            self._model_item(),
            self._statcast_item(),
            self._database_item(),
            self._odds_item(),
        ]
        critical_ok = all(item.state == "OK" for item in items if item.key in self._CRITICAL_KEYS)
        return HealthReport(items=tuple(items), critical_ok=critical_ok)

    def _model_item(self) -> HealthItem:
        package = self.service.package
        model_ok = bool(package.release_ready) and package.manifest.model_version == MODEL_VERSION
        detail = f"{package.manifest.model_version} validado." if model_ok else "Modelo no validado o versión inesperada."
        return HealthItem(key="model", label="Modelo", state="OK" if model_ok else "ERROR", detail=detail)

    def _statcast_item(self) -> HealthItem:
        statcast_ok = self.service.analytics.has_data()
        detail = "Datos disponibles." if statcast_ok else "Statcast no fue encontrado."
        return HealthItem(key="statcast", label="Statcast", state="OK" if statcast_ok else "ERROR", detail=detail)

    def _database_item(self) -> HealthItem:
        db_ok = self.store.healthcheck()
        detail = "Conexión OK." if db_ok else "No se pudo conectar a la base de datos local."
        return HealthItem(key="database", label="Base de datos", state="OK" if db_ok else "ERROR", detail=detail)

    def _odds_item(self) -> HealthItem:
        configured = self.service.odds is not None
        detail = "The Odds API configurado." if configured else "SIN API / NO CONFIGURADO."
        return HealthItem(key="odds", label="Cuotas", state="OK" if configured else "NOT_CONFIGURED", detail=detail)
