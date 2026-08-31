from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from mlb_hr.services.game_time import GameTimeService
from mlb_hr.services.history import (
    CombinationLegRecord,
    HistoryFilter,
    HistoryService,
)

MIN_ELIGIBLE_PROBABILITY = 0.05


@dataclass(frozen=True)
class PlayerAccuracyRecord:
    prediction_id: str
    player_name: str
    game_pk: int
    team_name: str
    opponent_name: str
    game_time_utc: datetime
    probability: float
    classification: str
    odds_at_prediction: int | None
    result: str
    pnl: float | None


@dataclass(frozen=True)
class CombinationAccuracyRecord:
    combination_id: str
    kind: str
    legs: tuple[CombinationLegRecord, ...]
    filter_status: str
    result: str
    odds: float | None
    pnl: float | None


@dataclass(frozen=True)
class DailyAccuracySummary:
    eligible_predictions: int
    resolved_predictions: int
    player_hits: int
    player_pending: int
    player_hit_rate: float | None
    combo_wins: int
    combo_pending: int


@dataclass(frozen=True)
class DailyAccuracyResult:
    players: tuple[PlayerAccuracyRecord, ...]
    combinations: tuple[CombinationAccuracyRecord, ...]
    summary: DailyAccuracySummary


class DailyAccuracyService:
    """Derives ACIERTOS HOY from the existing settlement/history evidence.

    Population and result derivation (NOT_ELIGIBLE exclusion, HR/NO_HR/PENDING,
    combination win-all-legs) are delegated entirely to HistoryService/the
    settlement path -- this only adds the day-scoping, the >=5% threshold, and
    the pregame-timing check the daily accuracy view specifically needs.
    """

    def __init__(self, store) -> None:
        self.store = store
        self.history = HistoryService(store)

    def for_date(self, local_date: date, timezone_name: str) -> DailyAccuracyResult:
        tz = GameTimeService(timezone_name)
        now = datetime.now(timezone.utc)
        all_filter = HistoryFilter(period="ALL", status="ALL", result="ALL")

        raw_rows_by_id = {row["prediction_id"]: row for row in self.store.history_prediction_rows()}

        players: list[PlayerAccuracyRecord] = []
        for rec in self.history.player_records(all_filter, now):
            if rec.game_time is None or rec.created_at is None:
                continue
            if rec.created_at >= rec.game_time:
                continue
            if rec.final_probability < MIN_ELIGIBLE_PROBABILITY:
                continue
            if tz.localize(rec.game_time).date() != local_date:
                continue
            raw = raw_rows_by_id.get(rec.prediction_id)
            if raw is None:
                continue
            players.append(PlayerAccuracyRecord(
                prediction_id=rec.prediction_id,
                player_name=rec.player_name,
                game_pk=int(raw["game_pk"]),
                team_name=raw["team_name"],
                opponent_name=raw["opponent_name"],
                game_time_utc=rec.game_time,
                probability=rec.final_probability,
                classification=rec.classification,
                odds_at_prediction=rec.odds_at_prediction,
                result=rec.result,
                pnl=rec.pnl,
            ))

        combinations: list[CombinationAccuracyRecord] = []
        for rec in self.history.combination_records(all_filter, now):
            anchor = rec.start_time or rec.created_at
            if anchor is None:
                continue
            if tz.localize(anchor).date() != local_date:
                continue
            combinations.append(CombinationAccuracyRecord(
                combination_id=rec.combination_id,
                kind=rec.kind,
                legs=tuple(rec.legs),
                filter_status=rec.filter_status,
                result=rec.result,
                odds=rec.estimated_decimal_odds,
                pnl=rec.pnl,
            ))

        resolved_players = [p for p in players if p.result in {"HR", "NO_HR"}]
        player_hits = sum(1 for p in resolved_players if p.result == "HR")
        player_pending = sum(1 for p in players if p.result == "PENDING")

        resolved_combos = [c for c in combinations if c.result in {"HR", "NO_HR"}]
        combo_wins = sum(1 for c in resolved_combos if c.result == "HR")
        combo_pending = sum(1 for c in combinations if c.result == "PENDING")

        summary = DailyAccuracySummary(
            eligible_predictions=len(players),
            resolved_predictions=len(resolved_players),
            player_hits=player_hits,
            player_pending=player_pending,
            player_hit_rate=(player_hits / len(resolved_players)) if resolved_players else None,
            combo_wins=combo_wins,
            combo_pending=combo_pending,
        )
        return DailyAccuracyResult(players=tuple(players), combinations=tuple(combinations), summary=summary)
