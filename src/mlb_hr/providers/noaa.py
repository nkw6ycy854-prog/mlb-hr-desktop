from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any

from mlb_hr.config import CONFIG
from mlb_hr.domain.enums import DataFreshness, RoofStatus
from mlb_hr.domain.models import ProviderMeta, VenueRef, WeatherSnapshot
from mlb_hr.providers.base import ProviderResult, now_utc
from mlb_hr.providers.http_client import HttpClient

_CARDINAL = {
    "N": 0.0,
    "NNE": 22.5,
    "NE": 45.0,
    "ENE": 67.5,
    "E": 90.0,
    "ESE": 112.5,
    "SE": 135.0,
    "SSE": 157.5,
    "S": 180.0,
    "SSW": 202.5,
    "SW": 225.0,
    "WSW": 247.5,
    "W": 270.0,
    "WNW": 292.5,
    "NW": 315.0,
    "NNW": 337.5,
}


class NOAAProvider:
    version = "1"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient(user_agent=CONFIG.user_agent)

    def forecast_for_game(self, game_pk: int, venue: VenueRef, game_time: datetime | None) -> ProviderResult[WeatherSnapshot]:
        fetched = now_utc()
        if venue.roof in {RoofStatus.CLOSED, RoofStatus.FIXED_DOME}:
            return ProviderResult(
                WeatherSnapshot(
                    game_pk=game_pk,
                    roof=venue.roof,
                    fetched_at=fetched,
                    reliability=0.98,
                    warnings=["Outdoor wind disabled because roof is closed/fixed."],
                ),
                self._meta(fetched),
            )
        if venue.latitude is None or venue.longitude is None:
            return ProviderResult(
                WeatherSnapshot(game_pk=game_pk, roof=venue.roof, fetched_at=fetched, reliability=0.25, warnings=["Venue coordinates unavailable."]),
                self._meta(fetched, complete=False),
                error_code="WEATHER_COORDINATES_MISSING",
                error_message="Venue coordinates unavailable",
            )
        try:
            point = self.http.get(f"{CONFIG.nws_base_url}/points/{venue.latitude:.4f},{venue.longitude:.4f}")
            props = point.json().get("properties", {})
            hourly_url = props.get("forecastHourly")
            if not hourly_url:
                raise ValueError("NWS points response missing forecastHourly")
            forecast = self.http.get(hourly_url)
            periods = forecast.json().get("properties", {}).get("periods", [])
            period = _nearest_period(periods, game_time)
            if period is None:
                raise ValueError("No NWS hourly period available")

            wind_speed = _parse_wind_speed(period.get("windSpeed"))
            wind_dir_text = period.get("windDirection")
            wind_dir_deg = _CARDINAL.get(str(wind_dir_text).upper())
            humidity = _nested_value(period, "relativeHumidity")
            precip = _nested_value(period, "probabilityOfPrecipitation")
            observed = _parse_dt(period.get("startTime"))
            snapshot = WeatherSnapshot(
                game_pk=game_pk,
                temperature_f=_float_or_none(period.get("temperature")),
                wind_mph=wind_speed,
                wind_direction_deg=wind_dir_deg,
                wind_text=wind_dir_text,
                humidity_pct=humidity,
                precip_probability_pct=precip,
                roof=venue.roof,
                observed_at=observed,
                fetched_at=fetched,
                reliability=0.90,
            )
            if venue.orientation_deg is not None and wind_dir_deg is not None and wind_speed is not None:
                # Wind direction is meteorological: direction the wind COMES FROM.
                toward = (wind_dir_deg + 180.0) % 360.0
                delta = math.radians((toward - venue.orientation_deg + 540.0) % 360.0 - 180.0)
                snapshot.wind_out_component = wind_speed * math.cos(delta)
                snapshot.wind_cross_component = wind_speed * math.sin(delta)
            else:
                snapshot.warnings.append("Stadium orientation unavailable; directional wind fit reduced.")
                snapshot.reliability = min(snapshot.reliability, 0.75)
            return ProviderResult(snapshot, self._meta(fetched), raw_reference=forecast.url)
        except Exception as exc:
            return ProviderResult(
                WeatherSnapshot(game_pk=game_pk, roof=venue.roof, fetched_at=fetched, reliability=0.2, warnings=[str(exc)]),
                self._meta(fetched, complete=False, warnings=[str(exc)]),
                error_code="PROVIDER_UNAVAILABLE",
                error_message=str(exc),
            )

    def _meta(self, fetched: datetime, complete: bool = True, warnings: list[str] | None = None) -> ProviderMeta:
        return ProviderMeta(
            provider="NOAA/NWS",
            fetched_at=fetched,
            freshness=DataFreshness.FRESH,
            complete=complete,
            warnings=warnings or [],
            provider_version=self.version,
        )


def _nearest_period(periods: list[dict[str, Any]], target: datetime | None) -> dict[str, Any] | None:
    if not periods:
        return None
    if target is None:
        return periods[0]
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    best = None
    best_delta = float("inf")
    for p in periods:
        dt = _parse_dt(p.get("startTime"))
        if dt is None:
            continue
        delta = abs((dt.astimezone(timezone.utc) - target.astimezone(timezone.utc)).total_seconds())
        if delta < best_delta:
            best, best_delta = p, delta
    return best


def _parse_wind_speed(value: Any) -> float | None:
    if value is None:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(value))]
    if not nums:
        return None
    return sum(nums[:2]) / min(len(nums), 2)


def _nested_value(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if isinstance(v, dict):
        return _float_or_none(v.get("value"))
    return _float_or_none(v)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
