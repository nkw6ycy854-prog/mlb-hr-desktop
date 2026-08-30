from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mlb_hr.domain.enums import DataFreshness, GameState, ModelHealth, SlateQuality
from mlb_hr.domain.models import GameContext, ProviderMeta, TeamLineup, VenueRef
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
    assert result.game_contexts == ()


def _confirmed_game(game_pk: int, state: GameState) -> GameContext:
    lineup = TeamLineup(team_id=1, team_name="A", entries=[], confirmed=True)
    return GameContext(
        game_pk=game_pk, game_date=date(2026, 8, 26), game_time=None,
        away_team_id=1, away_team_name="A", home_team_id=2, home_team_name="B",
        venue=VenueRef(1, "Park"), state=state,
        away_lineup=lineup, home_lineup=lineup,
    )


class _MLBWithGames:
    def __init__(self, games):
        self._games = games

    def schedule(self, _day):
        meta = ProviderMeta("TEST", datetime.now(timezone.utc), freshness=DataFreshness.FRESH)
        return ProviderResult(self._games, meta)

    def hydrate_game(self, game):
        meta = ProviderMeta("TEST", datetime.now(timezone.utc), freshness=DataFreshness.FRESH)
        return ProviderResult(game, meta)


def test_all_games_live_or_final_reports_zero_pregame_with_correct_message():
    # Reproduces the reported scenario: every game for "today" has already
    # started or finished. analyze_slate() must never fabricate picks for
    # them (the LIVE/FINAL exclusion stays), but it must report this
    # distinctly from "we analyzed pregame players and none qualified".
    service = object.__new__(AnalysisService)
    service.analytics = SimpleNamespace(has_data=lambda: True)
    service.mlb = _MLBWithGames([
        _confirmed_game(1, GameState.LIVE),
        _confirmed_game(2, GameState.LIVE),
        _confirmed_game(3, GameState.FINAL),
    ])
    service.package = SimpleNamespace(release_ready=True)
    service.ai = None
    service.ai_top_n = 0
    service.combos = SimpleNamespace(build=lambda _ranked: [])
    service.store = SimpleNamespace(
        save_combination=lambda _combo: None,
        invalidate_stale_predictions=lambda *a, **k: [],
    )

    result = service.analyze_slate(date(2026, 8, 26))

    assert result.cards == []
    assert result.pregame_games == 0
    assert result.live_games == 2
    assert result.final_games == 1
    assert any("NO HAY JUEGOS PREGAME DISPONIBLES PARA ANALIZAR" in m for m in result.messages)
    assert not any("NO HAY PICKS HR CALIFICADOS" in m for m in result.messages)
    assert [g.game_pk for g in result.game_contexts] == [1, 2, 3]
    assert [g.state for g in result.game_contexts] == [GameState.LIVE, GameState.LIVE, GameState.FINAL]


def test_missing_analytics_still_populates_game_contexts_for_hydrated_games():
    # Even when Statcast is unavailable and analyze_slate returns early with
    # no cards, the games it already hydrated from MLB must still be exposed
    # via game_contexts so POR PARTIDOS can render them (waiting-for-lineup,
    # LIVE, FINAL, etc.) instead of silently dropping the whole slate.
    service = object.__new__(AnalysisService)
    service.analytics = _MissingAnalytics()
    service.mlb = _MLBWithGames([_confirmed_game(7, GameState.PREGAME)])
    service.package = SimpleNamespace(release_ready=True)
    service.ai = None
    service.ai_top_n = 0
    service.combos = SimpleNamespace(build=lambda _ranked: [])
    service.store = SimpleNamespace(save_combination=lambda _combo: None)

    result = service.analyze_slate(date(2026, 8, 26))

    assert result.cards == []
    assert [g.game_pk for g in result.game_contexts] == [7]


def test_empty_picks_message_prioritizes_no_pregame_games_case():
    assert AnalysisService._empty_picks_message(pregame_games=0, confirmed=15) == \
        "NO HAY JUEGOS PREGAME DISPONIBLES PARA ANALIZAR"


def test_empty_picks_message_reports_no_qualified_picks_when_pregame_games_exist():
    assert AnalysisService._empty_picks_message(pregame_games=5, confirmed=5) == \
        "NO HAY PICKS HR CALIFICADOS ENTRE LOS JUEGOS CONFIRMADOS"


def test_empty_picks_message_reports_waiting_for_lineups_when_none_confirmed():
    assert AnalysisService._empty_picks_message(pregame_games=5, confirmed=0) == \
        "ESPERANDO LINEUPS CONFIRMADOS"
