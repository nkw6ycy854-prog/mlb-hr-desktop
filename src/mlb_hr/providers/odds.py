from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from mlb_hr.config import CONFIG
from mlb_hr.domain.enums import DataFreshness
from mlb_hr.domain.math import american_to_decimal, decimal_to_implied
from mlb_hr.domain.models import GameContext, OddsQuote, ProviderMeta
from mlb_hr.providers.base import ProviderResult, now_utc
from mlb_hr.providers.http_client import HttpClient


class OddsProvider:
    version = "1"

    def __init__(self, api_key: str | None, http: HttpClient | None = None) -> None:
        self.api_key = api_key
        self.http = http or HttpClient()
        self._events_cache: tuple[datetime, list[dict[str, Any]]] | None = None
        self._quote_cache: dict[int, tuple[datetime, list[OddsQuote]]] = {}

    def fetch_us_hr_quotes(self, game: GameContext) -> ProviderResult[list[OddsQuote]]:
        fetched = now_utc()
        if not self.api_key:
            return ProviderResult(
                [],
                self._meta(fetched, complete=False, warnings=["No Odds API key configured"]),
                error_code="ODDS_UNAVAILABLE",
                error_message="No Odds API key configured",
            )
        try:
            cached = self._quote_cache.get(game.game_pk)
            if cached and fetched - cached[0] < CONFIG.odds_fresh:
                return ProviderResult(list(cached[1]), self._meta(fetched), raw_reference="MEMORY_CACHE")
            if self._events_cache and fetched - self._events_cache[0] < CONFIG.odds_fresh:
                events = self._events_cache[1]
            else:
                events_r = self.http.get(
                    f"{CONFIG.odds_base_url}/sports/baseball_mlb/events",
                    params={"apiKey": self.api_key, "dateFormat": "iso"},
                )
                events = events_r.json()
                self._events_cache = (fetched, events)
            event = _match_event(events, game)
            if not event:
                return ProviderResult([], self._meta(fetched, complete=False, warnings=["No matching Odds API event"]), "ODDS_UNAVAILABLE", "No matching event")
            r = self.http.get(
                f"{CONFIG.odds_base_url}/sports/baseball_mlb/events/{event['id']}/odds",
                params={
                    "apiKey": self.api_key,
                    "regions": "us",
                    "markets": "batter_home_runs",
                    "oddsFormat": "american",
                    "dateFormat": "iso",
                },
            )
            quotes = _parse_quotes(r.json(), game, fetched)
            self._quote_cache[game.game_pk] = (fetched, list(quotes))
            return ProviderResult(quotes, self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult([], self._meta(fetched, complete=False, warnings=[str(exc)]), "ODDS_UNAVAILABLE", str(exc))

    def fetch_fanduel_hr_quotes(self, game: GameContext) -> ProviderResult[list[OddsQuote]]:
        result = self.fetch_us_hr_quotes(game)
        return ProviderResult(
            [q for q in (result.data or []) if q.bookmaker.lower() == "fanduel"],
            result.meta,
            result.error_code,
            result.error_message,
            result.raw_reference,
        )

    def _meta(self, fetched: datetime, complete: bool = True, warnings: list[str] | None = None) -> ProviderMeta:
        return ProviderMeta(
            provider="The Odds API",
            fetched_at=fetched,
            freshness=DataFreshness.FRESH,
            complete=complete,
            warnings=warnings or [],
            provider_version=self.version,
        )


def _normalize_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _match_event(events: list[dict[str, Any]], game: GameContext) -> dict[str, Any] | None:
    away = _normalize_team(game.away_team_name)
    home = _normalize_team(game.home_team_name)
    candidates = []
    for event in events:
        if _normalize_team(event.get("away_team", "")) == away and _normalize_team(event.get("home_team", "")) == home:
            candidates.append(event)
    if not candidates:
        return None
    if game.game_time is None:
        return candidates[0]
    target = game.game_time.astimezone(timezone.utc)
    def diff(e: dict[str, Any]) -> float:
        dt = _parse_dt(e.get("commence_time"))
        return abs((dt - target).total_seconds()) if dt else float("inf")
    return min(candidates, key=diff)


def _lineup_name_map(game: GameContext) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for lineup in (game.away_lineup, game.home_lineup):
        if not lineup:
            continue
        for e in lineup.entries:
            mapping[_normalize_person(e.player.full_name)] = e.player.player_id
    return mapping


def _normalize_person(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _parse_quotes(payload: dict[str, Any], game: GameContext, fetched: datetime) -> list[OddsQuote]:
    name_map = _lineup_name_map(game)
    out: list[OddsQuote] = []
    for book in payload.get("bookmakers", []):
        bookmaker = str(book.get("title") or book.get("key") or "Unknown")
        book_update = _parse_dt(book.get("last_update"))
        for market in book.get("markets", []):
            if market.get("key") != "batter_home_runs":
                continue
            market_update = _parse_dt(market.get("last_update")) or book_update
            freshness = _freshness(market_update, fetched)
            for o in market.get("outcomes", []):
                # The Odds API player prop schema normally uses name=Over/Under and description=player.
                selection = str(o.get("name", ""))
                if selection.lower() not in {"over", "yes"}:
                    continue
                point = _float_or_none(o.get("point"))
                if point is not None and point > 0.5:
                    continue
                player_name = str(o.get("description") or o.get("participant") or "")
                player_id = name_map.get(_normalize_person(player_name))
                if player_id is None:
                    continue
                try:
                    american = int(o["price"])
                    dec = american_to_decimal(american)
                except Exception:
                    continue
                out.append(
                    OddsQuote(
                        game_pk=game.game_pk,
                        player_id=player_id,
                        bookmaker=bookmaker,
                        market="batter_home_runs",
                        american_odds=american,
                        decimal_odds=dec,
                        implied_probability=decimal_to_implied(dec),
                        last_update=market_update,
                        fetched_at=fetched,
                        freshness=freshness,
                        source="THE_ODDS_API",
                        point=point,
                        selection_name=player_name,
                    )
                )
    return out


def _freshness(last_update: datetime | None, fetched: datetime) -> DataFreshness:
    if last_update is None:
        return DataFreshness.UNKNOWN
    age = fetched.astimezone(timezone.utc) - last_update.astimezone(timezone.utc)
    if age < CONFIG.odds_fresh:
        return DataFreshness.FRESH
    if age < CONFIG.odds_warning:
        return DataFreshness.WARNING
    return DataFreshness.STALE


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _float_or_none(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
