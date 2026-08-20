from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from mlb_hr.domain.enums import GameState, PlayerAppearanceStatus, SettlementStatus
from mlb_hr.domain.models import ResultRecord


@dataclass(slots=True)
class SettlementEvaluation:
    record: ResultRecord
    warnings: list[str]


class PostgameEngine:
    """Deterministic MLB official-feed settlement.

    A result is never inferred from score changes, news, or highlights. The terminal
    plate-appearance event and the official box score must reconcile before automatic
    settlement.
    """

    def evaluate(
        self,
        *,
        prediction_id: str,
        game_pk: int,
        player_id: int,
        feed: dict[str, Any],
        previous_result_version: int = 0,
    ) -> SettlementEvaluation:
        state = _state(feed)
        if state == GameState.POSTPONED:
            return SettlementEvaluation(ResultRecord(prediction_id,game_pk,player_id,SettlementStatus.POSTPONED,result_version=previous_result_version+1),[])
        if state == GameState.SUSPENDED:
            return SettlementEvaluation(ResultRecord(prediction_id,game_pk,player_id,SettlementStatus.SUSPENDED,result_version=previous_result_version+1),[])
        if state == GameState.CANCELLED:
            return SettlementEvaluation(ResultRecord(prediction_id,game_pk,player_id,SettlementStatus.CANCELLED,result_version=previous_result_version+1),[])
        if state == GameState.LIVE:
            return SettlementEvaluation(ResultRecord(prediction_id,game_pk,player_id,SettlementStatus.LIVE,result_version=previous_result_version+1),[])
        if state not in {GameState.FINAL}:
            return SettlementEvaluation(ResultRecord(prediction_id,game_pk,player_id,SettlementStatus.WAITING_FOR_GAME,result_version=previous_result_version+1),[])

        plays = feed.get("liveData",{}).get("plays",{}).get("allPlays",[]) or []
        player_plays=[p for p in plays if int((p.get("matchup",{}).get("batter") or {}).get("id",-1))==player_id and (p.get("about",{}).get("isComplete",True))]
        hr_count=sum(1 for p in player_plays if str(p.get("result",{}).get("eventType","")).lower()=="home_run")
        pa_count=len(player_plays)

        box = feed.get("liveData",{}).get("boxscore",{}).get("teams",{}) or {}
        box_stats=None
        starter_ids:set[int]=set()
        appeared=False
        started=False
        for side in ("away","home"):
            team=box.get(side,{}) or {}
            pitchers=team.get("pitchers",[]) or []
            if pitchers:
                starter_ids.add(int(pitchers[0]))
            players=team.get("players",{}) or {}
            row=players.get(f"ID{player_id}")
            if row:
                appeared=True
                bo=str(row.get("battingOrder") or "")
                started=bo.endswith("00") and len(bo)>=3
                box_stats=(row.get("stats",{}) or {}).get("batting",{}) or {}
                break

        sp_pa=0;bp_pa=0
        for p in player_plays:
            pid=(p.get("matchup",{}).get("pitcher") or {}).get("id")
            if pid is not None and int(pid) in starter_ids:sp_pa+=1
            else:bp_pa+=1

        box_hr=_int_or_none((box_stats or {}).get("homeRuns"))
        box_pa=_int_or_none((box_stats or {}).get("plateAppearances"))
        verified_pbp=True
        verified_box=box_stats is not None
        warnings=[]
        conflict=False
        if box_hr is not None and box_hr!=hr_count:
            conflict=True;warnings.append(f"PBP HR={hr_count} vs box HR={box_hr}")
        if box_pa is not None and box_pa!=pa_count:
            # Some rare scoring/appearance edge cases can differ temporarily; require review rather than guessing.
            conflict=True;warnings.append(f"PBP PA={pa_count} vs box PA={box_pa}")

        if not appeared and pa_count==0:
            appearance=PlayerAppearanceStatus.DID_NOT_APPEAR
        elif started and pa_count>0:
            appearance=PlayerAppearanceStatus.STARTED_AND_BATTED
        elif appeared and pa_count>0:
            appearance=PlayerAppearanceStatus.SUBSTITUTED
        elif started:
            appearance=PlayerAppearanceStatus.STARTED_NO_COMPLETED_PA
        else:
            appearance=PlayerAppearanceStatus.UNKNOWN

        if conflict:
            status=SettlementStatus.REVIEW_REQUIRED
        elif pa_count==0 and appearance==PlayerAppearanceStatus.DID_NOT_APPEAR:
            status=SettlementStatus.VOID
            warnings.append("Player did not appear; not counted as predictive miss.")
        else:
            status=SettlementStatus.PROVISIONAL_SETTLEMENT

        return SettlementEvaluation(
            ResultRecord(
                prediction_id=prediction_id,
                game_pk=game_pk,
                player_id=player_id,
                status=status,
                actual_hr_count=hr_count,
                actual_hr_binary=1 if hr_count>=1 else 0,
                actual_pa=pa_count,
                actual_pa_vs_starter=sp_pa,
                actual_pa_vs_bullpen=bp_pa,
                appearance_status=appearance,
                verified_pbp=verified_pbp,
                verified_box=verified_box,
                result_version=previous_result_version+1,
                result_source="MLB_OFFICIAL_GAME_FEED",
                fetched_at=datetime.now(timezone.utc),
            ),
            warnings,
        )

    def confirm_unchanged(self, record: ResultRecord) -> ResultRecord:
        if record.status != SettlementStatus.PROVISIONAL_SETTLEMENT:
            return record
        return ResultRecord(
            prediction_id=record.prediction_id,
            game_pk=record.game_pk,
            player_id=record.player_id,
            status=SettlementStatus.CONFIRMED_SETTLEMENT,
            actual_hr_count=record.actual_hr_count,
            actual_hr_binary=record.actual_hr_binary,
            actual_pa=record.actual_pa,
            actual_pa_vs_starter=record.actual_pa_vs_starter,
            actual_pa_vs_bullpen=record.actual_pa_vs_bullpen,
            appearance_status=record.appearance_status,
            verified_pbp=record.verified_pbp,
            verified_box=record.verified_box,
            result_version=record.result_version+1,
            result_source=record.result_source,
            fetched_at=datetime.now(timezone.utc),
            change_reason="OFFICIAL_RECHECK_UNCHANGED",
        )


def _state(feed: dict[str,Any])->GameState:
    status=feed.get("gameData",{}).get("status",{}) or {}
    abstract=str(status.get("abstractGameState","")).lower()
    detailed=str(status.get("detailedState","")).lower()
    if "postpon" in detailed:return GameState.POSTPONED
    if "suspend" in detailed:return GameState.SUSPENDED
    if "cancel" in detailed:return GameState.CANCELLED
    if abstract=="final":return GameState.FINAL
    if abstract=="live":return GameState.LIVE
    return GameState.PREGAME


def _int_or_none(v:Any)->int|None:
    try:return int(v)
    except (TypeError,ValueError):return None
