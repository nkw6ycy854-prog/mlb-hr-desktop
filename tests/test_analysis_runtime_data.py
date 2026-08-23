from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mlb_hr.domain.enums import DataFreshness, ModelHealth, SlateQuality
from mlb_hr.domain.models import ProviderMeta
from mlb_hr.providers.base import ProviderResult
from mlb_hr.services.analysis import AnalysisService


class _MissingAnalytics:
    parquet_dir = Path("/missing/statcast")

    def has_data(self) -> bool:
        return False


class _EmptyMLB:
    def schedule(self, _day):
        meta = ProviderMeta("TEST", datetime.now(timezone.utc), freshness=DataFreshness.FRESH)
        return ProviderResult([], meta)


def test_missing_runtime_statcast_is_reported_explicitly():
    service = object.__new__(AnalysisService)
    service.analytics = _MissingAnalytics()
    service.mlb = _EmptyMLB()
    service.package = SimpleNamespace(release_ready=True)
    service.ai = None
    service.ai_top_n = 0
    service.combos = SimpleNamespace(build=lambda _ranked: [])
    service.store = SimpleNamespace(save_combination=lambda _combo: None)

    result = service.analyze_slate(date(2026, 8, 21))

    assert result.cards == []
    assert result.slate_quality == SlateQuality.RED
    assert result.model_health == ModelHealth.GREEN
    assert any("DATOS HISTÓRICOS NO DISPONIBLES" in message for message in result.messages)
