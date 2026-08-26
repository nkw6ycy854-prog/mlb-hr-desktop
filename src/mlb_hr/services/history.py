from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json


@dataclass(frozen=True)
class HistoryFilter:
    period: str = "ALL"        # TODAY | 7D | 30D | ALL
    status: str = "ALL"        # ALL | RECOMMENDED | WATCH | NO_FILTER
    result: str = "ALL"        # ALL | HR | NO_HR | PENDING


@dataclass(frozen=True)
class PlayerHistoryRecord:
    prediction_id: str
    player_name: str
    game_time: datetime | None
    created_at: datetime
    classification: str
    status: str
    final_probability: float
    reference_stake: float | None
    odds_at_prediction: int | None
    result: str
    pnl: float | None


@dataclass(frozen=True)
class CombinationLegRecord:
    player_name: str
    classification: str
    game_pk: int
    game_time: datetime | None


@dataclass(frozen=True)
class CombinationHistoryRecord:
    combination_id: str
    kind: str
    created_at: datetime
    start_time: datetime | None
    filter_status: str
    status: str
    result: str
    pnl: float | None
    estimated_decimal_odds: float | None
    legs: list[CombinationLegRecord]


_PLAYER_STATUS_BY_CLASSIFICATION = {
    "PRIMARY": "RECOMMENDED",
    "SECONDARY": "RECOMMENDED",
    "WATCH": "WATCH",
    "NO_BET": "NO_FILTER",
}


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _within_period(dt: datetime | None, period: str, now: datetime) -> bool:
    if period == "ALL" or dt is None:
        return True
    if period == "TODAY":
        return dt.astimezone(now.tzinfo or timezone.utc).date() == now.date()
    if period == "7D":
        return dt >= now - timedelta(days=7)
    if period == "30D":
        return dt >= now - timedelta(days=30)
    return True


class HistoryService:
    def __init__(self, store) -> None:
        self.store = store

    def player_records(self, filter: HistoryFilter, now: datetime) -> list[PlayerHistoryRecord]:
        rows = self.store.history_prediction_rows()
        records: list[PlayerHistoryRecord] = []
        for row in rows:
            status = _PLAYER_STATUS_BY_CLASSIFICATION.get(row["classification"])
            if status is None:
                continue  # NOT_ELIGIBLE rows are never surfaced as history evidence to bet on
            hr_binary = row["actual_hr_binary"]
            result = "PENDING" if hr_binary is None else ("HR" if int(hr_binary) == 1 else "NO_HR")
            record = PlayerHistoryRecord(
                prediction_id=row["prediction_id"],
                player_name=row["player_name"],
                game_time=_parse_dt(row["game_time"]),
                created_at=_parse_dt(row["created_at"]),
                classification=row["classification"],
                status=status,
                final_probability=float(row["final_probability"]),
                reference_stake=row["reference_stake"],
                odds_at_prediction=row["odds_at_prediction"],
                result=result,
                pnl=row["pnl_amount"],
            )
            period_anchor = record.game_time or record.created_at
            if not _within_period(period_anchor, filter.period, now):
                continue
            if filter.status != "ALL" and record.status != filter.status:
                continue
            if filter.result != "ALL" and record.result != filter.result:
                continue
            records.append(record)
        return records

    def combination_records(self, filter: HistoryFilter, now: datetime) -> list[CombinationHistoryRecord]:
        rows = self.store.history_combination_rows()
        parsed_legs_by_combo = {row["combination_id"]: json.loads(row["legs_json"]) for row in rows}
        all_leg_ids = {leg["prediction_id"] for legs in parsed_legs_by_combo.values() for leg in legs}
        prediction_rows = self.store.prediction_rows_by_ids(list(all_leg_ids))

        records: list[CombinationHistoryRecord] = []
        for row in rows:
            legs_raw = parsed_legs_by_combo[row["combination_id"]]
            leg_records: list[CombinationLegRecord] = []
            game_times: list[datetime] = []
            for leg in legs_raw:
                pred_row = prediction_rows.get(leg["prediction_id"])
                game_time = _parse_dt(pred_row["game_time"]) if pred_row else None
                if game_time is not None:
                    game_times.append(game_time)
                leg_records.append(CombinationLegRecord(
                    player_name=leg["player_name"],
                    classification=leg["classification"],
                    game_pk=leg["game_pk"],
                    game_time=game_time,
                ))
            filter_status = row["filter_status"]
            status = "RECOMMENDED" if filter_status == "QUALIFIED" else "NO_FILTER"
            won = row["won"]
            result = "PENDING" if won is None else ("HR" if int(won) == 1 else "NO_HR")
            start_time = min(game_times) if game_times else None
            record = CombinationHistoryRecord(
                combination_id=row["combination_id"],
                kind=row["kind"],
                created_at=_parse_dt(row["created_at"]),
                start_time=start_time,
                filter_status=filter_status,
                status=status,
                result=result,
                pnl=row["profit_loss"],
                estimated_decimal_odds=row["estimated_decimal_odds"],
                legs=leg_records,
            )
            period_anchor = record.start_time or record.created_at
            if not _within_period(period_anchor, filter.period, now):
                continue
            if filter.status != "ALL" and record.status != filter.status:
                continue
            if filter.result != "ALL" and record.result != filter.result:
                continue
            records.append(record)
        return records

    @staticmethod
    def summarize_players(records: list[PlayerHistoryRecord]) -> dict:
        resolved = [r for r in records if r.result in {"HR", "NO_HR"}]
        hits = sum(1 for r in resolved if r.result == "HR")
        pnl = sum(r.pnl or 0 for r in records)
        staked = sum(
            r.reference_stake for r in resolved
            if r.odds_at_prediction is not None and r.reference_stake is not None
        )
        return {
            "analyzed": len(records),
            "recommended": sum(1 for r in records if r.status == "RECOMMENDED"),
            "hits": hits,
            "hit_rate": hits / len(resolved) if resolved else None,
            "pnl": pnl,
            "roi": pnl / staked if staked else None,
        }

    @staticmethod
    def summarize_combinations(records: list[CombinationHistoryRecord]) -> dict:
        resolved = [r for r in records if r.result in {"HR", "NO_HR"}]
        hits = sum(1 for r in resolved if r.result == "HR")
        pnl = sum(r.pnl or 0 for r in records)
        return {
            "analyzed": len(records),
            "recommended": sum(1 for r in records if r.status == "RECOMMENDED"),
            "hits": hits,
            "hit_rate": hits / len(resolved) if resolved else None,
            "pnl": pnl,
        }
