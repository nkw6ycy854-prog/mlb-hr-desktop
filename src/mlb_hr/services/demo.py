from __future__ import annotations

from datetime import datetime, timezone, timedelta

from mlb_hr.domain.enums import (
    ConfidenceLabel, CriticVerdict, DataFreshness, IntegrityStatus, MarketPriceLabel,
    ModelClassification, ModelHealth, SlateQuality, UserActionLabel,
)
from mlb_hr.domain.models import (
    MarketDecision, OddsQuote, PlayerRef, Prediction, PredictionCard, ProbabilityDistribution, SlateResult,
)
from mlb_hr.combinations.engine import CombinationEngine
from mlb_hr.odds.market import MarketLayer


class DemoAnalysisService:
    """UI-only demo. Never used for real predictions."""
    def __init__(self, stake: float = 10.0) -> None:
        self.stake=stake;self.market=MarketLayer();self.combos=CombinationEngine()

    def analyze_slate(self, day=None)->SlateResult:
        now=datetime.now(timezone.utc)
        specs=[
            ("Player A",24.8,88,310,ModelClassification.PRIMARY,["Abridor vulnerable al HR","Perfil de lanzamientos favorable","Buena exposición esperada contra el abridor"],"Bullpen posterior menos favorable"),
            ("Player B",22.6,84,360,ModelClassification.PRIMARY,["Potencia HR por encima de la liga","Matchup de handedness favorable","Parque favorable para su perfil"],None),
            ("Player C",20.1,67,290,ModelClassification.SECONDARY,["Buen encaje contra la velocidad del abridor","Zonas de ataque favorables"],"Muestra específica moderada"),
            ("Player D",18.8,74,190,ModelClassification.SECONDARY,["Matchup general favorable"],"Precio de mercado poco atractivo"),
        ]
        cards=[]
        for i,(name,pct,conf,odds,cls,reasons,risk) in enumerate(specs,1):
            p=pct/100
            pred=Prediction(
                prediction_id=f"demo-{i}",snapshot_id=f"demo-snap-{i}",game_pk=900000+i,
                player=PlayerRef(1000+i,name,bat_side="R"),opposing_pitcher=PlayerRef(2000+i,f"Pitcher {i}",throw_side="R"),
                team_name="TEAM",opponent_name="OPP",game_time=now+timedelta(hours=2+i),
                final_hr_probability=p,raw_hr_probability=p,matchup_score=82-i,grade="A-",reliability=80,
                confidence_score=conf,confidence_label=ConfidenceLabel.HIGH if conf>=75 else ConfidenceLabel.MEDIUM,
                distribution=ProbabilityDistribution(p,p-.025,p,p+.025,.05,85),classification=cls,
                user_action=UserActionLabel.RECOMMENDED if cls in {ModelClassification.PRIMARY,ModelClassification.SECONDARY} else UserActionLabel.OPTIONAL,
                integrity=IntegrityStatus.PASS,critic=CriticVerdict.PASS,reasons=reasons,main_risk=risk,warnings=[],
                model_version="DEMO",feature_version="DEMO",calibration_version="DEMO",quality_gate_version="DEMO",model_health=ModelHealth.GREEN,
            )
            dec=1+odds/100
            quote=OddsQuote(pred.game_pk,pred.player.player_id,"FanDuel","batter_home_runs",odds,dec,1/dec,now-timedelta(minutes=3),now,DataFreshness.FRESH,"DEMO")
            market=self.market.evaluate(p,quote,self.stake)
            cards.append(PredictionCard(pred,market))
        return SlateResult(cards,self.combos.build(cards),SlateQuality.GREEN,ModelHealth.GREEN,15,15,now,["MODO DEMO — datos ficticios, no apostar con estos resultados."])

    def apply_manual_odds(self,card,american_odds):
        quote=self.market.manual_quote(card.prediction.game_pk,card.prediction.player.player_id,american_odds)
        card.market=self.market.evaluate(card.prediction.final_hr_probability,quote,self.stake)
        return card
