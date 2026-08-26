from datetime import date, datetime, timezone

from mlb_hr.domain.models import GameContext, LineupEntry, PlayerRef, TeamLineup, VenueRef
from mlb_hr.providers.odds import OddsProvider, _parse_quotes


def _game() -> GameContext:
    batter = PlayerRef(player_id=1, full_name="Aaron Judge")
    lineup = TeamLineup(team_id=1, team_name="Yankees", entries=[LineupEntry(batter, 1)], confirmed=True)
    return GameContext(
        game_pk=100,
        game_date=date(2026, 8, 26),
        game_time=datetime(2026, 8, 26, 19, 5, tzinfo=timezone.utc),
        away_team_id=1,
        away_team_name="Yankees",
        home_team_id=2,
        home_team_name="Red Sox",
        venue=VenueRef(1, "Yankee Stadium"),
        away_lineup=lineup,
    )


def _payload() -> dict:
    return {
        "bookmakers": [
            {
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": "2026-08-26T18:00:00Z",
                "markets": [
                    {
                        "key": "batter_home_runs",
                        "last_update": "2026-08-26T18:00:00Z",
                        "outcomes": [
                            {"name": "Over", "description": "Aaron Judge", "price": 390, "point": 0.5},
                        ],
                    }
                ],
            },
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": "2026-08-26T18:00:00Z",
                "markets": [
                    {
                        "key": "batter_home_runs",
                        "last_update": "2026-08-26T18:00:00Z",
                        "outcomes": [
                            {"name": "Yes", "description": "Aaron Judge", "price": 430, "point": 0.5},
                        ],
                    }
                ],
            },
        ]
    }


def test_parses_all_us_bookmaker_hr_quotes():
    game = _game()
    now = datetime(2026, 8, 26, 18, 5, tzinfo=timezone.utc)
    quotes = _parse_quotes(_payload(), game, now)
    assert {(q.bookmaker, q.american_odds) for q in quotes} == {
        ("FanDuel", 390),
        ("DraftKings", 430),
    }


class _FakeResponse:
    def __init__(self, payload: dict | list, url: str) -> None:
        self._payload = payload
        self.url = url

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self, events_payload, odds_payload) -> None:
        self.events_payload = events_payload
        self.odds_payload = odds_payload
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, url, *, params=None, headers=None, max_bytes=None):
        self.calls.append((url, params))
        if url.endswith("/events"):
            return _FakeResponse(self.events_payload, url)
        return _FakeResponse(self.odds_payload, url)


def _events_payload():
    return [
        {
            "id": "evt1",
            "away_team": "Yankees",
            "home_team": "Red Sox",
            "commence_time": "2026-08-26T19:05:00Z",
        }
    ]


def test_fetch_us_hr_quotes_requests_all_us_books_without_bookmaker_filter():
    game = _game()
    http = FakeHttpClient(_events_payload(), _payload())
    provider = OddsProvider(api_key="key123", http=http)

    provider.fetch_us_hr_quotes(game)

    odds_call = next(call for call in http.calls if "/odds" in call[0])
    params = odds_call[1]
    assert params["regions"] == "us"
    assert params["markets"] == "batter_home_runs"
    assert params["oddsFormat"] == "american"
    assert "bookmakers" not in params


def test_fetch_fanduel_hr_quotes_filters_from_all_us_books():
    game = _game()
    http = FakeHttpClient(_events_payload(), _payload())
    provider = OddsProvider(api_key="key123", http=http)

    result = provider.fetch_fanduel_hr_quotes(game)

    assert {(q.bookmaker, q.american_odds) for q in result.data} == {("FanDuel", 390)}
