from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mlb_hr.domain.enums import ModelClassification
from mlb_hr.domain.models import PredictionCard, SlateResult, TeamLineup
from mlb_hr.ui.presentation import practical_status

_INELIGIBLE_PRACTICAL_STATUS = "NO ELEGIBLE"


@dataclass(frozen=True)
class PlayerGameView:
    player_id: int
    player_name: str
    hr_probability: float | None
    classification: str
    confidence: str
    practical_status: str
    eligible: bool
    card: PredictionCard | None
    batting_order: int


@dataclass(frozen=True)
class TeamGameView:
    team_name: str
    lineup_confirmed: bool
    players: tuple[PlayerGameView, ...]


@dataclass(frozen=True)
class GamePredictionView:
    game_pk: int
    away: TeamGameView
    home: TeamGameView
    game_time_utc: datetime | None
    game_state: str
    ready: bool
    empty_message: str | None


class GamePredictionViewBuilder:
    def build(self, slate: SlateResult, timezone_name: str) -> tuple[GamePredictionView, ...]:
        cards_by_player: dict[tuple[int, int], PredictionCard] = {
            (card.prediction.game_pk, card.prediction.player.player_id): card for card in slate.cards
        }
        views = []
        for game in slate.game_contexts:
            away = self._team_view(game.away_lineup, game.game_pk, cards_by_player)
            home = self._team_view(game.home_lineup, game.game_pk, cards_by_player)
            ready = away.lineup_confirmed and home.lineup_confirmed and game.state.value == "PREGAME"
            empty_message = self._empty_message(game.state.value, ready)
            views.append(GamePredictionView(
                game_pk=game.game_pk, away=away, home=home,
                game_time_utc=game.game_time, game_state=game.state.value,
                ready=ready, empty_message=empty_message,
            ))
        return tuple(views)

    def _team_view(
        self, lineup: TeamLineup | None, game_pk: int, cards_by_player: dict[tuple[int, int], PredictionCard],
    ) -> TeamGameView:
        if lineup is None:
            return TeamGameView(team_name="", lineup_confirmed=False, players=())
        # V1.2.0: real batting order 1-9, not an HR%-ranked/eligible-first
        # presentation -- a pure display-order change, never touches which
        # players are included or any predictive value.
        players = sorted(
            (self._player_view(entry, game_pk, cards_by_player) for entry in lineup.entries),
            key=lambda p: p.batting_order,
        )
        return TeamGameView(
            team_name=lineup.team_name, lineup_confirmed=lineup.confirmed, players=tuple(players),
        )

    def _player_view(
        self, entry, game_pk: int, cards_by_player: dict[tuple[int, int], PredictionCard],
    ) -> PlayerGameView:
        card = cards_by_player.get((game_pk, entry.player.player_id))
        eligible = card is not None and card.prediction.classification != ModelClassification.NOT_ELIGIBLE
        if eligible:
            pred = card.prediction
            return PlayerGameView(
                player_id=entry.player.player_id, player_name=entry.player.full_name,
                hr_probability=pred.final_hr_probability, classification=pred.classification.value,
                confidence=pred.confidence_label.value, practical_status=practical_status(pred.classification),
                eligible=True, card=card, batting_order=entry.batting_order,
            )
        return PlayerGameView(
            player_id=entry.player.player_id, player_name=entry.player.full_name,
            hr_probability=None, classification=ModelClassification.NOT_ELIGIBLE.value,
            confidence="—", practical_status=_INELIGIBLE_PRACTICAL_STATUS, eligible=False, card=None,
            batting_order=entry.batting_order,
        )

    @staticmethod
    def _empty_message(game_state: str, ready: bool) -> str | None:
        if ready:
            return None
        if game_state in ("LIVE", "FINAL"):
            estado = "EN VIVO" if game_state == "LIVE" else "FINAL"
            return f"{estado} — Predicciones pregame cerradas."
        return "ESPERANDO LINEUP CONFIRMADO. Predicciones disponibles cuando ambos lineups estén confirmados."
