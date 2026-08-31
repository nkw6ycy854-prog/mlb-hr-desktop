from __future__ import annotations

from datetime import datetime, timezone, timedelta

from mlb_hr.domain.enums import SettlementStatus
from mlb_hr.domain.models import ResultRecord
from mlb_hr.postgame.engine import PostgameEngine
from mlb_hr.providers.mlb import MLBProvider
from mlb_hr.storage.sqlite import SQLiteStore


def _materially_same(active_row, rec: ResultRecord) -> bool:
    """Whether a freshly-evaluated result carries the same real-world content
    as the currently active settlement row, ignoring bookkeeping fields
    (result_version, fetched_at, change_reason). Comparing only this -- never
    timestamps -- is what makes a re-check of an unchanged provisional result
    a no-op instead of a new version.
    """
    return (
        active_row["status"] == rec.status.value
        and active_row["actual_hr_count"] == rec.actual_hr_count
        and active_row["actual_hr_binary"] == rec.actual_hr_binary
        and active_row["actual_pa"] == rec.actual_pa
        and active_row["actual_pa_vs_starter"] == rec.actual_pa_vs_starter
        and active_row["actual_pa_vs_bullpen"] == rec.actual_pa_vs_bullpen
        and active_row["appearance_status"] == rec.appearance_status.value
        and active_row["verified_pbp"] == int(rec.verified_pbp)
        and active_row["verified_box"] == int(rec.verified_box)
        and active_row["result_source"] == rec.result_source
    )


class SettlementService:
    def __init__(self,store:SQLiteStore,mlb:MLBProvider|None=None)->None:
        self.store=store;self.mlb=mlb or MLBProvider();self.engine=PostgameEngine()

    def reconcile_pending(self)->dict[str,int]:
        rows=self.store.pending_predictions();stats={"checked":0,"settled":0,"waiting":0,"review":0,"errors":0}
        feeds={}
        for row in rows:
            game_pk=int(row["game_pk"])
            if game_pk not in feeds:
                r=self.mlb.game_feed(game_pk);feeds[game_pk]=r.data if r.ok else None
            feed=feeds[game_pk]
            if feed is None:
                stats["errors"]+=1;continue
            stats["checked"]+=1
            active=self.store.active_settlement(row["prediction_id"])
            prev_version=int(active["result_version"]) if active else 0
            evaluation=self.engine.evaluate(prediction_id=row["prediction_id"],game_pk=game_pk,player_id=int(row["player_id"]),feed=feed,previous_result_version=prev_version)
            rec=evaluation.record
            if active and active["status"]==SettlementStatus.PROVISIONAL_SETTLEMENT.value:
                fetched=datetime.fromisoformat(active["fetched_at"])
                if fetched.tzinfo is None:fetched=fetched.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc)-fetched>=timedelta(hours=24) and rec.status==SettlementStatus.PROVISIONAL_SETTLEMENT and _materially_same(active,rec):
                    base=ResultRecord(
                        prediction_id=row["prediction_id"],game_pk=game_pk,player_id=int(row["player_id"]),
                        status=SettlementStatus.PROVISIONAL_SETTLEMENT,actual_hr_count=rec.actual_hr_count,actual_hr_binary=rec.actual_hr_binary,
                        actual_pa=rec.actual_pa,actual_pa_vs_starter=rec.actual_pa_vs_starter,actual_pa_vs_bullpen=rec.actual_pa_vs_bullpen,
                        appearance_status=rec.appearance_status,verified_pbp=rec.verified_pbp,verified_box=rec.verified_box,
                        result_version=prev_version,result_source=rec.result_source,fetched_at=fetched,
                    )
                    rec=self.engine.confirm_unchanged(base)
            # Avoid version churn for unchanged non-final waiting states.
            if active and active["status"]==rec.status.value and rec.status not in {SettlementStatus.CONFIRMED_SETTLEMENT,SettlementStatus.PROVISIONAL_SETTLEMENT,SettlementStatus.REVIEW_REQUIRED}:
                stats["waiting"]+=1;continue
            # A provisional/review-required re-check whose real content hasn't
            # changed at all is not a new fact -- do not version it. Only a
            # material difference (or the terminal confirm above, which
            # reassigns rec.status to CONFIRMED_SETTLEMENT) reaches save_settlement.
            if active and rec.status in {SettlementStatus.PROVISIONAL_SETTLEMENT,SettlementStatus.REVIEW_REQUIRED} and _materially_same(active,rec):
                stats["waiting"]+=1;continue
            if active and rec.status==SettlementStatus.PROVISIONAL_SETTLEMENT and active["status"]==SettlementStatus.PROVISIONAL_SETTLEMENT.value:
                self.store.log_audit(
                    module="settlement",severity="INFO",event_code="PROVISIONAL_SETTLEMENT_CHANGED",
                    payload={
                        "previous":{"actual_hr_count":active["actual_hr_count"],"actual_hr_binary":active["actual_hr_binary"],"actual_pa":active["actual_pa"]},
                        "new":{"actual_hr_count":rec.actual_hr_count,"actual_hr_binary":rec.actual_hr_binary,"actual_pa":rec.actual_pa},
                    },
                    prediction_id=row["prediction_id"],game_pk=game_pk,
                )
            self.store.save_settlement(rec)
            if rec.status==SettlementStatus.CONFIRMED_SETTLEMENT:
                stats["settled"]+=1
                if rec.actual_hr_binary is not None:self.store.apply_paper_settlement(rec.prediction_id,bool(rec.actual_hr_binary))
            elif rec.status==SettlementStatus.REVIEW_REQUIRED:stats["review"]+=1
            else:stats["waiting"]+=1
        combo_stats=self.reconcile_combinations()
        stats.update({f"combo_{k}":v for k,v in combo_stats.items()})
        return stats

    def reconcile_combinations(self)->dict[str,int]:
        import json
        from mlb_hr.domain.math import payout_for_stake
        stats={"checked":0,"settled":0,"waiting":0,"void":0}
        for row in self.store.pending_combinations():
            legs=json.loads(row["legs_json"] or "[]")
            ids=[str(x.get("prediction_id")) for x in legs if x.get("prediction_id")]
            settled=self.store.leg_settlements(ids);stats["checked"]+=1
            if len(settled)<len(ids):stats["waiting"]+=1;continue
            statuses=[settled[x]["status"] for x in ids]
            voids=sum(1 for x in statuses if x in {SettlementStatus.VOID.value,SettlementStatus.CANCELLED.value,SettlementStatus.POSTPONED.value})
            if voids:
                self.store.save_combination_settlement(row["combination_id"],status=SettlementStatus.VOID.value,won=None,void_leg_count=voids,profit_loss=None);stats["void"]+=1;continue
            if not all(x==SettlementStatus.CONFIRMED_SETTLEMENT.value for x in statuses):stats["waiting"]+=1;continue
            won=all(int(settled[x]["actual_hr_binary"] or 0)==1 for x in ids)
            pl=None
            if row["actual_parlay_odds"] is not None:
                stake=10.0
                _,profit=payout_for_stake(stake,int(row["actual_parlay_odds"]));pl=profit if won else -stake
            self.store.save_combination_settlement(row["combination_id"],status=SettlementStatus.CONFIRMED_SETTLEMENT.value,won=won,void_leg_count=0,profit_loss=pl);stats["settled"]+=1
        return stats
