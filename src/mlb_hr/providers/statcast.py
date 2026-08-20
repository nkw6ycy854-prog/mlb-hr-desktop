from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from typing import Any

from mlb_hr.config import CONFIG
from mlb_hr.domain.enums import DataFreshness
from mlb_hr.domain.models import ProviderMeta
from mlb_hr.providers.base import ProviderResult, now_utc
from mlb_hr.providers.http_client import HttpClient


class StatcastProvider:
    version = "1"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()

    def fetch_day(self, day: date, *, game_type: str = "R") -> ProviderResult[list[dict[str, str]]]:
        """Fetch one Statcast game date.

        The historical bootstrap operates on immutable day partitions, so keep the
        public one-day helper explicit instead of making callers duplicate the
        Baseball Savant date-range contract.
        """
        return self.fetch_date_range(day, day, game_type=game_type)

    def fetch_date_range(self, start: date, end: date, *, game_type: str = "R") -> ProviderResult[list[dict[str, str]]]:
        fetched = now_utc()
        params = {
            "all": "true",
            "type": "details",
            "game_date_gt": start.isoformat(),
            "game_date_lt": end.isoformat(),
            "hfGT": f"{game_type}|",
            "player_type": "batter",
            "min_pitches": 0,
            "min_results": 0,
            "min_pas": 0,
            "sort_col": "pitches",
            "sort_order": "desc",
        }
        try:
            r = self.http.get(CONFIG.savant_csv_url, params=params, max_bytes=100 * 1024 * 1024)
            text = r.text.lstrip("\ufeff")
            rows = list(csv.DictReader(StringIO(text)))
            return ProviderResult(rows, self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult(
                None,
                self._meta(fetched, complete=False, warnings=[str(exc)]),
                error_code="PROVIDER_UNAVAILABLE",
                error_message=str(exc),
            )

    def _meta(self, fetched: datetime, complete: bool = True, warnings: list[str] | None = None) -> ProviderMeta:
        return ProviderMeta(
            provider="Baseball Savant/Statcast",
            fetched_at=fetched,
            freshness=DataFreshness.FRESH,
            complete=complete,
            warnings=warnings or [],
            provider_version=self.version,
        )
