from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from mlb_hr.ai.coordinator import AutoFreeAI
from mlb_hr.combinations.engine import CombinationEngine
from mlb_hr.config import CONFIG
from mlb_hr.domain.enums import (
    CriticVerdict,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    ModelHealth,
    SlateQuality,
    WarningSeverity,
)
from mlb_hr.domain.models import (
    DataWarning,
    GameContext,
    MarketDecision,
    Prediction,
    PredictionCard,
    SlateResult,
)
from mlb_hr.features.engine import CandidateFeatureBundle, FeatureEngine
from mlb_hr.integrity.checks import DataIntegrityEngine
from mlb_hr.model.inference import ProbabilityEngine
from mlb_hr.model.package import ModelPackage
from mlb_hr.odds.market import MarketLayer
from mlb_hr.providers.mlb import MLBProvider
from mlb_hr.providers.noaa import NOAAProvider
from mlb_hr.providers.odds import OddsProvider
from mlb_hr.quality_gates.critic import CriticResult, LocalModelCritic
from mlb_hr.quality_gates.engine import QualityGateEngine
from mlb_hr.storage.analytics import AnalyticsStore
from mlb_hr.storage.sqlite import SQLiteStore
from mlb_hr.uncertainty.engine import UncertaintyEngine

_EXCLUDED_GAME_STATES = {"LIVE", "FINAL", "POSTPONED", "SUSPENDED", "CANCELLED"}


class AnalysisService:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        analytics: AnalyticsStore,
        model_package: ModelPackage,
        mlb: MLBProvider | None = None,
        noaa: NOAAProvider | None = None,
        odds: OddsProvider | None = None,
        ai: AutoFreeAI | None = None,
        ai_top_n: int = 12,
        stake: float = 10.0,
        allow_unvalidated_demo: bool = False,
    ) -> None:
        self.store=store;self.analytics=analytics;self.package=model_package
        self.mlb=mlb or MLBProvider();self.noaa=noaa or NOAAProvider();self.odds=odds
        self.ai=ai;self.ai_top_n=max(0,int(ai_top_n));self.stake=stake
        feature_config=model_package.feature_config
        feature_config["_enabled_model_features"]=list(model_package.manifest.feature_names)
        self.features=FeatureEngine(analytics,feature_config)
        self.prob=ProbabilityEngine(model_package)
        self.unc=UncertaintyEngine(self.prob)
        self.integrity=DataIntegrityEngine()
        self.critic=LocalModelCritic()
        self.gates=QualityGateEngine(model_package,allow_unvalidated_demo=allow_unvalidated_demo)
        self.market=MarketLayer();self.combos=CombinationEngine()

    def analyze_slate(self, day: date | None = None) -> SlateResult:
        day=day or datetime.now().date()
        schedule=self.mlb.schedule(day)
        if not schedule.ok:
            return SlateResult([],[],SlateQuality.RED,ModelHealth.RED,0,0,datetime.now(timezone.utc),0,0,0,["MLB schedule unavailable"])
        games=schedule.data or []
        hydrated: list[GameContext]=[]
        for game in games:
            r=self.mlb.hydrate_game(game)
            hydrated.append(r.data if r.ok and r.data is not None else game)
        confirmed=sum(1 for g in hydrated if g.away_lineup and g.away_lineup.confirmed and g.home_lineup and g.home_lineup.confirmed)
        pregame_games=sum(1 for g in hydrated if g.state.value not in _EXCLUDED_GAME_STATES)
        live_games=sum(1 for g in hydrated if g.state.value=="LIVE")
        final_games=sum(1 for g in hydrated if g.state.value=="FINAL")
        slate_quality=SlateQuality.GREEN if confirmed==len(hydrated) and hydrated else SlateQuality.YELLOW
        model_health=ModelHealth.GREEN if self.package.release_ready else ModelHealth.YELLOW
        if not self.analytics.has_data():
            messages=[
                "DATOS HISTÓRICOS NO DISPONIBLES: el análisis HR está bloqueado hasta que Statcast local esté disponible."
            ]
            pending=max(0,len(hydrated)-confirmed)
            if confirmed<len(hydrated):
                messages.append(
                    f"{confirmed}/{len(hydrated)} JUEGOS LISTOS · {pending} ESPERANDO LINEUP."
                )
            return SlateResult(
                [],[],SlateQuality.RED,model_health,confirmed,len(hydrated),datetime.now(timezone.utc),
                pregame_games,live_games,final_games,messages,
            )
        predictive_cards: list[PredictionCard]=[]
        ai_context: dict[str,tuple[CandidateFeatureBundle,object,CriticResult,list[DataWarning]]]={}
        game_lookup: dict[int,GameContext]={g.game_pk:g for g in hydrated}
        change_messages: list[str]=[]

        for game in hydrated:
            if game.state.value in _EXCLUDED_GAME_STATES:
                continue
            if (game.away_lineup and game.away_lineup.confirmed and game.home_lineup and game.home_lineup.confirmed
                    and game.away_starter is not None and game.home_starter is not None):
                valid_matchups={e.player.player_id:game.home_starter.player_id for e in game.away_lineup.entries}
                valid_matchups.update({e.player.player_id:game.away_starter.player_id for e in game.home_lineup.entries})
                for ch in self.store.invalidate_stale_predictions(game.game_pk,valid_matchups):
                    if ch['reason']=='POST_LOCK_LINEUP_INVALIDATION':
                        change_messages.append(f"{ch['player_name']} fue eliminado del lineup confirmado.")
                    else:
                        change_messages.append(f"Cambió el abridor para el matchup de {ch['player_name']}; se recalcula.")
            # Enrich venue coordinates. A failure degrades weather, not MLB lineup integrity.
            venue_r=self.mlb.venue_details(game.venue.venue_id) if game.venue.venue_id else None
            if venue_r and venue_r.ok and venue_r.data:
                # Preserve any manually/versioned orientation already present.
                orientation=game.venue.orientation_deg
                game.venue=venue_r.data
                game.venue.orientation_deg=orientation
            weather_r=self.noaa.forecast_for_game(game.game_pk,game.venue,game.game_time)
            weather=weather_r.data
            rosters: dict[int,set[int]|None]={}
            for team_id in (game.away_team_id,game.home_team_id):
                rr=self.mlb.active_roster(team_id)
                rosters[team_id]={p.player_id for p in (rr.data or [])} if rr.ok else None

            sides=[
                (game.away_lineup,game.home_starter,game.away_team_name,game.home_team_name,game.home_team_id,game.home_team_abbr),
                (game.home_lineup,game.away_starter,game.home_team_name,game.away_team_name,game.away_team_id,game.away_team_abbr),
            ]
            for lineup,starter,team_name,opp_name,opp_team_id,opp_abbr in sides:
                entries=lineup.entries if lineup and lineup.confirmed else []
                if not entries:
                    continue
                for entry in entries:
                    integ=self.integrity.check_candidate(
                        game=game,lineup=entry,starter=starter,
                        analytics_available=self.analytics.has_data(),allow_started=False,
                    )
                    if integ.status!=IntegrityStatus.PASS or starter is None:
                        continue
                    snapshot_id=str(uuid4())
                    bundle=self.features.build(
                        game=game,batter_entry=entry,opposing_pitcher=starter,weather=weather,
                        opponent_team_abbr=opp_abbr,active_bullpen_ids=rosters.get(opp_team_id),snapshot_id=snapshot_id,
                    )
                    inf=self.prob.predict(bundle)
                    unc=self.unc.evaluate(bundle,inf.final_probability)
                    critic=self.critic.review(bundle,unc)
                    warnings=[*integ.warnings,*bundle.vector.warnings]
                    outcheck=self.integrity.validate_probability_output(
                        raw=inf.raw_game_probability,final=inf.final_probability,
                        p10=unc.distribution.p10,p50=unc.distribution.p50,p90=unc.distribution.p90,
                    )
                    warnings.extend(outcheck.warnings)
                    final_integrity=IntegrityStatus.FAIL if outcheck.status==IntegrityStatus.FAIL else integ.status
                    gate=self.gates.classify(
                        integrity=final_integrity,probability=inf.final_probability,matchup_score=inf.matchup_score,
                        uncertainty=unc,critic=critic,warnings=warnings,model_health=model_health,
                    )
                    reasons=self._explain(bundle,gate.reasons)
                    risk=critic.main_risk or self._risk_from_warnings(warnings)
                    pred=Prediction(
                        prediction_id=Prediction.new_id(),snapshot_id=snapshot_id,game_pk=game.game_pk,
                        player=entry.player,opposing_pitcher=starter,team_name=team_name,opponent_name=opp_name,
                        game_time=game.game_time,final_hr_probability=inf.final_probability,
                        raw_hr_probability=inf.raw_game_probability,matchup_score=inf.matchup_score,grade=inf.grade,
                        reliability=unc.component_reliability.get("HISTORY",0)*100,
                        confidence_score=unc.confidence_score,confidence_label=unc.confidence_label,
                        distribution=unc.distribution,classification=gate.classification,user_action=gate.user_action,
                        integrity=final_integrity,critic=critic.verdict,reasons=reasons,main_risk=risk,warnings=warnings,
                        model_version=self.package.manifest.model_version,feature_version=self.package.manifest.feature_version,
                        calibration_version=self.package.manifest.calibration_version,quality_gate_version=self.package.manifest.quality_gate_version,
                        model_health=model_health,created_at=datetime.now(timezone.utc),
                    )
                    self.store.save_snapshot(
                        snapshot_id=snapshot_id,game_pk=game.game_pk,
                        lineup={"player_id":entry.player.player_id,"batting_order":entry.batting_order,"confirmed":True},
                        starter={"player_id":starter.player_id,"name":starter.full_name},
                        weather=asdict(weather) if weather else None,
                        source_timestamps={"mlb":game.fetched_at,"weather":weather.fetched_at if weather else None},
                        feature_vector={"values":bundle.vector.values,"reliabilities":bundle.vector.reliabilities},
                        model_package_hash=self.package.package_hash,deterministic_seed=self.package.manifest.deterministic_seed,
                        created_at=pred.created_at,
                    )
                    self.store.save_prediction(pred,tracked=gate.classification!=ModelClassification.NOT_ELIGIBLE)
                    # Market layer intentionally deferred until all predictive outputs are locked.
                    predictive_cards.append(PredictionCard(pred,MarketDecision(None,MarketPriceLabel.NO_ODDS)))
                    ai_context[pred.prediction_id]=(bundle,unc,critic,warnings)

        # Optional Agent-8 style AI review is strictly post-probability and pre-market.
        # It can only downgrade/flag a predictive classification; it never changes probability.
        ai_review_unavailable=False
        if self.ai is not None and self.package.release_ready and self.ai_top_n>0:
            reviewable=sorted(
                [c for c in predictive_cards if c.prediction.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}],
                key=self._rank_key,reverse=True,
            )[:self.ai_top_n]
            for card in reviewable:
                p=card.prediction;bundle,unc,local_critic,warnings=ai_context[p.prediction_id]
                payload={
                    "snapshot_id":p.snapshot_id,"game_pk":p.game_pk,"batter_id":p.player.player_id,
                    "pitcher_id":p.opposing_pitcher.player_id,"final_hr_probability":p.final_hr_probability,
                    "confidence_score":p.confidence_score,"confidence_label":p.confidence_label.value,
                    "p10":p.distribution.p10,"p50":p.distribution.p50,"p90":p.distribution.p90,
                    "matchup_score":p.matchup_score,"local_critic":local_critic.verdict.value,
                    "warning_codes":[w.code for w in warnings],
                    "feature_values":bundle.vector.values,"feature_reliabilities":bundle.vector.reliabilities,
                }
                review=self.ai.review("MODEL_CRITIC",payload)
                self.store.log_audit(
                    module="ai",severity="INFO" if review.available else "WARNING",
                    event_code="AI_MODEL_CRITIC_REVIEW" if review.available else "AI_REVIEW_UNAVAILABLE",
                    payload={"provider":review.provider,"model":review.model,"verdict":review.verdict,"reasons":review.reasons,"error":review.error},
                    snapshot_id=p.snapshot_id,prediction_id=p.prediction_id,game_pk=p.game_pk,
                )
                if not review.available:
                    ai_review_unavailable=True
                    break  # avoid burning multiple failing calls on the same refresh
                ai_verdict={"PASS":CriticVerdict.PASS,"CAUTION":CriticVerdict.CAUTION,"REJECT":CriticVerdict.REJECT}.get(review.verdict,CriticVerdict.CAUTION)
                severity={CriticVerdict.PASS:0,CriticVerdict.CAUTION:1,CriticVerdict.REJECT:2}
                merged_verdict=max((local_critic.verdict,ai_verdict),key=lambda v:severity[v])
                merged=CriticResult(
                    merged_verdict,
                    [*local_critic.reasons,*([f"AI_{r}" for r in (review.reasons or [])] if ai_verdict!=CriticVerdict.PASS else [])],
                    local_critic.main_risk or ((review.reasons or [None])[0] if ai_verdict!=CriticVerdict.PASS else None),
                )
                gate=self.gates.classify(
                    integrity=p.integrity,probability=p.final_hr_probability,matchup_score=p.matchup_score,
                    uncertainty=unc,critic=merged,warnings=warnings,model_health=p.model_health,
                )
                if gate.classification!=p.classification or merged_verdict!=p.critic:
                    revised=replace(
                        p,prediction_id=Prediction.new_id(),classification=gate.classification,user_action=gate.user_action,
                        critic=merged_verdict,main_risk=merged.main_risk or p.main_risk,created_at=datetime.now(timezone.utc),
                    )
                    self.store.save_prediction(revised,tracked=gate.classification!=ModelClassification.NOT_ELIGIBLE)
                    card.prediction=revised

        # Odds are fetched only after predictive qualification. The prediction object is never
        # recomputed from price. WATCH/NO_BET rows are still pregame-locked for calibration
        # tracking, but they do not consume odds quota.
        self._assign_market_and_odds(predictive_cards,game_lookup)

        for card in predictive_cards:
            p=card.prediction
            if p.classification==ModelClassification.NOT_ELIGIBLE:
                continue
            quote=card.market.quote
            self.store.save_model_ledger(
                prediction_id=p.prediction_id,reference_stake=self.stake,
                odds_at_prediction=quote.american_odds if quote else None,
                decimal_odds=quote.decimal_odds if quote else None,
                implied_probability=quote.implied_probability if quote else None,
                edge_pp=card.market.edge_pp,user_bet=False,
            )
            self.store.lock_prediction(p.prediction_id)
        ranked=sorted(predictive_cards,key=self._rank_key,reverse=True)
        combos=self.combos.build(ranked)
        for combo in combos:
            self.store.save_combination(combo)
        messages=list(dict.fromkeys(change_messages))
        if not self.package.release_ready:
            messages.append("MODEL PACKAGE NO VALIDADO: no se emiten apuestas reales hasta completar walk-forward/holdout.")
        if ai_review_unavailable:
            messages.append("AI REVIEW UNAVAILABLE: el análisis determinista permanece activo.")
        pending=max(0,len(hydrated)-confirmed)
        if confirmed<len(hydrated):
            messages.append(
                f"{confirmed}/{len(hydrated)} JUEGOS LISTOS · {pending} ESPERANDO LINEUP. "
                "Analizando únicamente juegos con ambos lineups confirmados."
            )
        if not any(c.prediction.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY} for c in ranked):
            messages.append(self._empty_picks_message(pregame_games,confirmed))
        return SlateResult(
            ranked,combos,slate_quality,model_health,confirmed,len(hydrated),datetime.now(timezone.utc),
            pregame_games,live_games,final_games,messages,
        )

    @staticmethod
    def _empty_picks_message(pregame_games:int,confirmed:int)->str:
        if pregame_games==0:
            return "NO HAY JUEGOS PREGAME DISPONIBLES PARA ANALIZAR"
        if confirmed>0:
            return "NO HAY PICKS HR CALIFICADOS ENTRE LOS JUEGOS CONFIRMADOS"
        return "ESPERANDO LINEUPS CONFIRMADOS"

    def _assign_market_and_odds(self,predictive_cards:list[PredictionCard],game_lookup:dict[int,GameContext])->None:
        by_game: dict[int,list[PredictionCard]]={}
        for card in predictive_cards:
            if card.prediction.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}:
                by_game.setdefault(card.prediction.game_pk,[]).append(card)
        for game_pk,cards in by_game.items():
            game=game_lookup[game_pk]
            quotes=[]
            if self.odds is not None:
                qres=self.odds.fetch_us_hr_quotes(game)
                quotes=qres.data or []
            by_player: dict[int,list] = {}
            for quote in quotes:
                by_player.setdefault(quote.player_id,[]).append(quote)
            for card in cards:
                player_quotes=by_player.get(card.prediction.player.player_id,[])
                fanduel_quote=next((quote for quote in player_quotes if quote.bookmaker.lower()=="fanduel"),None)
                best_quote=max(
                    (quote for quote in player_quotes if quote.decimal_odds is not None),
                    key=lambda quote:quote.decimal_odds,
                    default=None,
                )
                card.market=self.market.evaluate(card.prediction.final_hr_probability,fanduel_quote,self.stake)
                card.best_market=self.market.evaluate(card.prediction.final_hr_probability,best_quote,self.stake)
                for quote in player_quotes:
                    self.store.save_odds(quote,card.prediction.prediction_id,is_at_prediction=False)
                if fanduel_quote:
                    self.store.save_odds(fanduel_quote,card.prediction.prediction_id,is_at_prediction=True)

    def apply_manual_odds(self, card: PredictionCard, american_odds: int) -> PredictionCard:
        if card.prediction.classification not in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}:
            raise ValueError("La cuota manual solo se aplica a candidatos ya cualificados por el modelo.")
        quote=self.market.manual_quote(card.prediction.game_pk,card.prediction.player.player_id,american_odds)
        card.market=self.market.evaluate(card.prediction.final_hr_probability,quote,self.stake)
        self.store.save_odds(quote,card.prediction.prediction_id,is_at_prediction=True)
        self.store.save_model_ledger(
            prediction_id=card.prediction.prediction_id,reference_stake=self.stake,
            odds_at_prediction=quote.american_odds,decimal_odds=quote.decimal_odds,
            implied_probability=quote.implied_probability,edge_pp=card.market.edge_pp,user_bet=False,
        )
        return card

    @staticmethod
    def _rank_key(card:PredictionCard)->tuple:
        p=card.prediction
        class_rank={ModelClassification.PRIMARY:4,ModelClassification.SECONDARY:3,ModelClassification.WATCH:2,ModelClassification.NO_BET:1,ModelClassification.NOT_ELIGIBLE:0}[p.classification]
        return (class_rank,p.final_hr_probability,p.confidence_score,p.matchup_score)

    def _explain(self,b:CandidateFeatureBundle,gate_reasons:Iterable[str])->list[str]:
        v=b.vector.values;out=[]
        if v.get("pitcher_hr_bf",0)>b.league_hr_pa*1.15:out.append("Abridor vulnerable al HR")
        if v.get("batter_hr_pa",0)>b.league_hr_pa*1.25:out.append("Potencia HR del bateador por encima de la liga")
        if v.get("pitch_type_match",0)>0.04:out.append("Perfil de lanzamientos favorable")
        if v.get("velocity_match",0)>0.04:out.append("Buen encaje contra la velocidad del abridor")
        if v.get("zone_match",0)>0.04:out.append("Zonas de ataque favorables")
        if v.get("similar_pitcher_delta",0)>0.008:out.append("Buen historial contra pitchers de perfil similar")
        if v.get("batter_platoon_delta",0)+v.get("pitcher_platoon_delta",0)>0.008:out.append("Matchup de handedness favorable")
        out.extend(b.park.reasons)
        if b.starter_exposure.expected_pa_vs_starter>=2.2:out.append("Buena exposición esperada contra el abridor")
        if not out:
            out.append("Perfil general de potencia y matchup favorable")
        return out[:4]

    @staticmethod
    def _risk_from_warnings(warnings:list[DataWarning])->str|None:
        majors=[w for w in warnings if w.severity==WarningSeverity.MAJOR]
        if majors:return majors[0].message
        minors=[w for w in warnings if w.severity==WarningSeverity.MINOR]
        return minors[0].message if minors else None
