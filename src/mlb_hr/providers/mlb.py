from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from mlb_hr.config import CONFIG
from mlb_hr.domain.enums import DataFreshness, GameState, RoofStatus
from mlb_hr.domain.models import (
    GameContext,
    LineupEntry,
    PlayerRef,
    ProviderMeta,
    TeamLineup,
    VenueRef,
)
from mlb_hr.providers.base import ProviderResult, now_utc
from mlb_hr.providers.http_client import HttpClient


class MLBProvider:
    version = "1"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()

    def _meta(self, fetched: datetime, complete: bool = True, warnings: list[str] | None = None) -> ProviderMeta:
        return ProviderMeta(
            provider="MLB",
            fetched_at=fetched,
            freshness=DataFreshness.FRESH,
            complete=complete,
            warnings=warnings or [],
            provider_version=self.version,
        )

    def schedule(self, day: date) -> ProviderResult[list[GameContext]]:
        fetched = now_utc()
        try:
            r = self.http.get(
                f"{CONFIG.mlb_base_url}/api/v1/schedule",
                params={
                    "sportId": 1,
                    "date": day.isoformat(),
                    "hydrate": "team,probablePitcher,venue",
                },
            )
            payload = r.json()
            games: list[GameContext] = []
            for d in payload.get("dates", []):
                for g in d.get("games", []):
                    teams = g.get("teams", {})
                    away = teams.get("away", {}).get("team", {})
                    home = teams.get("home", {}).get("team", {})
                    venue = g.get("venue", {})
                    game_time = _parse_dt(g.get("gameDate"))
                    status = g.get("status", {})
                    games.append(
                        GameContext(
                            game_pk=int(g["gamePk"]),
                            game_date=day,
                            game_time=game_time,
                            away_team_id=int(away.get("id", 0)),
                            away_team_name=away.get("name", "Away"),
                            away_team_abbr=away.get("abbreviation"),
                            home_team_id=int(home.get("id", 0)),
                            home_team_name=home.get("name", "Home"),
                            home_team_abbr=home.get("abbreviation"),
                            venue=VenueRef(
                                venue_id=int(venue.get("id", 0)),
                                name=venue.get("name", "Unknown Venue"),
                            ),
                            state=_game_state(status),
                            away_starter=_player_from_probable(teams.get("away", {}).get("probablePitcher")),
                            home_starter=_player_from_probable(teams.get("home", {}).get("probablePitcher")),
                            fetched_at=fetched,
                            raw_status=status.get("detailedState"),
                        )
                    )
            return ProviderResult(games, self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult(
                None,
                self._meta(fetched, complete=False, warnings=[str(exc)]),
                error_code="PROVIDER_UNAVAILABLE",
                error_message=str(exc),
            )

    def hydrate_game(self, game: GameContext) -> ProviderResult[GameContext]:
        fetched = now_utc()
        try:
            r = self.http.get(f"{CONFIG.mlb_base_url}/api/v1.1/game/{game.game_pk}/feed/live")
            payload = r.json()
            gd = payload.get("gameData", {})
            ld = payload.get("liveData", {})
            status = gd.get("status", {})
            game.state = _game_state(status)
            game.raw_status = status.get("detailedState")
            teams_gd = gd.get("teams", {})
            game.away_team_abbr = (teams_gd.get("away") or {}).get("abbreviation") or game.away_team_abbr
            game.home_team_abbr = (teams_gd.get("home") or {}).get("abbreviation") or game.home_team_abbr
            game.fetched_at = fetched

            venue_data = gd.get("venue", {})
            if venue_data:
                game.venue.venue_id = int(venue_data.get("id", game.venue.venue_id or 0))
                game.venue.name = venue_data.get("name", game.venue.name)

            prob = gd.get("probablePitchers", {})
            players = gd.get("players", {})
            if prob.get("away"):
                game.away_starter = _player_from_gamedata(prob["away"], players)
            if prob.get("home"):
                game.home_starter = _player_from_gamedata(prob["home"], players)

            box_teams = ld.get("boxscore", {}).get("teams", {})
            game.away_lineup = _parse_lineup(
                box_teams.get("away", {}), players, game.away_team_id, game.away_team_name
            )
            game.home_lineup = _parse_lineup(
                box_teams.get("home", {}), players, game.home_team_id, game.home_team_name
            )

            # Prefer the announced starter if MLB's boxscore already identifies the first pitcher.
            away_pitchers = box_teams.get("away", {}).get("pitchers", [])
            home_pitchers = box_teams.get("home", {}).get("pitchers", [])
            if away_pitchers and game.state in {GameState.LIVE, GameState.FINAL}:
                game.away_starter = _player_by_id(int(away_pitchers[0]), players)
            if home_pitchers and game.state in {GameState.LIVE, GameState.FINAL}:
                game.home_starter = _player_by_id(int(home_pitchers[0]), players)

            return ProviderResult(game, self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult(
                None,
                self._meta(fetched, complete=False, warnings=[str(exc)]),
                error_code="PROVIDER_UNAVAILABLE",
                error_message=str(exc),
            )

    def venue_details(self, venue_id: int) -> ProviderResult[VenueRef]:
        fetched = now_utc()
        try:
            r = self.http.get(
                f"{CONFIG.mlb_base_url}/api/v1/venues/{venue_id}",
                params={"hydrate": "location"},
            )
            venues = r.json().get("venues", [])
            if not venues:
                raise ValueError(f"Venue {venue_id} not found")
            v = venues[0]
            loc = v.get("location", {})
            coords = loc.get("defaultCoordinates", {}) or {}
            roof_text = str(v.get("fieldInfo", {}).get("roofType", "")).lower()
            roof = RoofStatus.UNKNOWN
            if "dome" in roof_text or "fixed" in roof_text:
                roof = RoofStatus.FIXED_DOME
            return ProviderResult(
                VenueRef(
                    venue_id=venue_id,
                    name=v.get("name", "Unknown Venue"),
                    latitude=_float_or_none(coords.get("latitude")),
                    longitude=_float_or_none(coords.get("longitude")),
                    roof=roof,
                ),
                self._meta(fetched),
                raw_reference=r.url,
            )
        except Exception as exc:
            return ProviderResult(
                None,
                self._meta(fetched, complete=False, warnings=[str(exc)]),
                error_code="PROVIDER_UNAVAILABLE",
                error_message=str(exc),
            )

    def active_roster(self, team_id: int) -> ProviderResult[list[PlayerRef]]:
        fetched = now_utc()
        try:
            r = self.http.get(
                f"{CONFIG.mlb_base_url}/api/v1/teams/{team_id}/roster",
                params={"rosterType": "active"},
            )
            players = []
            for row in r.json().get("roster", []):
                person = row.get("person", {})
                if person.get("id"):
                    players.append(PlayerRef(int(person["id"]), person.get("fullName", str(person["id"])), team_id=team_id))
            return ProviderResult(players, self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult(None, self._meta(fetched, complete=False), "PROVIDER_UNAVAILABLE", str(exc))

    def game_feed(self, game_pk: int) -> ProviderResult[dict[str, Any]]:
        fetched = now_utc()
        try:
            r = self.http.get(f"{CONFIG.mlb_base_url}/api/v1.1/game/{game_pk}/feed/live")
            return ProviderResult(r.json(), self._meta(fetched), raw_reference=r.url)
        except Exception as exc:
            return ProviderResult(None, self._meta(fetched, complete=False), "PROVIDER_UNAVAILABLE", str(exc))


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


def _game_state(status: dict[str, Any]) -> GameState:
    abstract = str(status.get("abstractGameState", "")).lower()
    detailed = str(status.get("detailedState", "")).lower()
    coded = str(status.get("codedGameState", "")).upper()
    if "postpon" in detailed:
        return GameState.POSTPONED
    if "suspend" in detailed:
        return GameState.SUSPENDED
    if "cancel" in detailed:
        return GameState.CANCELLED
    if abstract == "live" or coded in {"I", "M"}:
        return GameState.LIVE
    if abstract == "final" or coded in {"F", "O"}:
        return GameState.FINAL
    if abstract == "preview" or "pre-game" in detailed or "warmup" in detailed:
        return GameState.PREGAME
    if coded in {"S", "P"}:
        return GameState.SCHEDULED
    return GameState.UNKNOWN


def _player_from_probable(data: dict[str, Any] | None) -> PlayerRef | None:
    if not data or not data.get("id"):
        return None
    return PlayerRef(int(data["id"]), data.get("fullName", str(data["id"])))


def _player_from_gamedata(data: dict[str, Any], players: dict[str, Any]) -> PlayerRef | None:
    if not data.get("id"):
        return None
    return _player_by_id(int(data["id"]), players)


def _player_by_id(player_id: int, players: dict[str, Any]) -> PlayerRef:
    row = players.get(f"ID{player_id}", {})
    return PlayerRef(
        player_id=player_id,
        full_name=row.get("fullName", row.get("firstName", str(player_id))),
        bat_side=(row.get("batSide") or {}).get("code"),
        throw_side=(row.get("pitchHand") or {}).get("code"),
    )


def _parse_lineup(team_box: dict[str, Any], players: dict[str, Any], team_id: int, team_name: str) -> TeamLineup:
    order = team_box.get("battingOrder") or []
    team_players = team_box.get("players") or {}
    entries: list[LineupEntry] = []
    for idx, pid in enumerate(order[:9], start=1):
        pid = int(pid)
        p = _player_by_id(pid, players)
        p.team_id = team_id
        box_p = team_players.get(f"ID{pid}", {})
        position = (box_p.get("position") or {}).get("abbreviation")
        entries.append(LineupEntry(player=p, batting_order=idx, position=position, confirmed=True))
    return TeamLineup(team_id=team_id, team_name=team_name, entries=entries, confirmed=len(entries) == 9)
