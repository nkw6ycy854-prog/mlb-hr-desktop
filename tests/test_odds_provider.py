from datetime import date, datetime, timezone

from mlb_hr.domain.models import GameContext, LineupEntry, PlayerRef, TeamLineup, VenueRef
from mlb_hr.providers.odds import _parse_quotes


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
