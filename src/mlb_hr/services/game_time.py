from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class GameTimeService:
    DEFAULT_TIMEZONE = "America/Santo_Domingo"

    def __init__(self, timezone_name: str = DEFAULT_TIMEZONE) -> None:
        self.timezone_name = timezone_name
        self._zone = ZoneInfo(timezone_name)

    def localize(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("game_time must be timezone-aware")
        return value.astimezone(self._zone)

    def format_time(self, value: datetime | None) -> str:
        if value is None:
            return "—"
        text = self.localize(value).strftime("%I:%M %p")
        return text.lstrip("0") or text

    def format_date(self, value: datetime | None) -> str:
        if value is None:
            return "—"
        return self.localize(value).strftime("%Y-%m-%d")
