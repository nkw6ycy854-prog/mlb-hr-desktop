from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from mlb_hr.domain.enums import GameState, IntegrityStatus, WarningSeverity
from mlb_hr.domain.models import DataWarning, GameContext, LineupEntry, PlayerRef


@dataclass(slots=True)
class IntegrityResult:
    status: IntegrityStatus
    warnings: list[DataWarning] = field(default_factory=list)


class DataIntegrityEngine:
    def check_candidate(
        self,
        *,
        game: GameContext,
        lineup: LineupEntry | None,
        starter: PlayerRef | None,
        analytics_available: bool,
        allow_started: bool = False,
    ) -> IntegrityResult:
        w: list[DataWarning] = []
        if game.state in {GameState.LIVE, GameState.FINAL} and not allow_started:
            w.append(DataWarning("GAME_ALREADY_STARTED", WarningSeverity.CRITICAL, "El juego ya comenzó", "GAME"))
        if game.state in {GameState.POSTPONED, GameState.CANCELLED, GameState.SUSPENDED}:
            w.append(DataWarning("GAME_NOT_ELIGIBLE_STATE", WarningSeverity.CRITICAL, f"Estado del juego: {game.state.value}", "GAME"))
        if lineup is None:
            w.append(DataWarning("LINEUP_NOT_CONFIRMED", WarningSeverity.CRITICAL, "Lineup titular no confirmado", "LINEUP"))
        if starter is None:
            w.append(DataWarning("STARTER_NOT_CONFIRMED", WarningSeverity.CRITICAL, "Pitcher abridor no confirmado", "STARTER"))
        if not analytics_available:
            w.append(DataWarning("HISTORICAL_DATA_UNAVAILABLE", WarningSeverity.CRITICAL, "Historial Statcast local no disponible", "DATA"))
        if game.fetched_at is None:
            w.append(DataWarning("GAME_CONTEXT_TIMESTAMP_MISSING", WarningSeverity.MAJOR, "Timestamp de contexto MLB ausente", "DATA"))
        elif game.game_time is not None:
            now = datetime.now(timezone.utc)
            fetched = game.fetched_at if game.fetched_at.tzinfo else game.fetched_at.replace(tzinfo=timezone.utc)
            if game.game_time.astimezone(timezone.utc) - now < timedelta(hours=2) and (now - fetched).total_seconds() > 180:
                w.append(DataWarning("CRITICAL_CONTEXT_STALE", WarningSeverity.CRITICAL, "Lineup/SP demasiado antiguos cerca del juego", "DATA"))
        status = IntegrityStatus.FAIL if any(x.severity == WarningSeverity.CRITICAL for x in w) else IntegrityStatus.PASS
        return IntegrityResult(status, w)

    def validate_probability_output(self, *, raw: float, final: float, p10: float, p50: float, p90: float) -> IntegrityResult:
        w=[]
        if not (0 <= raw <= 1 and 0 <= final <= 1):
            w.append(DataWarning("PROBABILITY_OUT_OF_RANGE", WarningSeverity.CRITICAL, "Probabilidad fuera de [0,1]", "MODEL"))
        if not (0 <= p10 <= p50 <= p90 <= 1):
            w.append(DataWarning("UNCERTAINTY_ORDER_INVALID", WarningSeverity.CRITICAL, "P10/P50/P90 incoherentes", "UNCERTAINTY"))
        return IntegrityResult(IntegrityStatus.FAIL if w else IntegrityStatus.PASS,w)
