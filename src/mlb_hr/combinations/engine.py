from __future__ import annotations

from itertools import combinations
import math
from uuid import uuid4

from mlb_hr.domain.enums import ModelClassification
from mlb_hr.domain.models import Combination, CombinationLeg, PredictionCard


class CombinationEngine:
    def build(self, cards: list[PredictionCard]) -> list[Combination]:
        eligible=[c for c in cards if c.prediction.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}]
        out: list[Combination]=[]
        best2=self._best(eligible,2,"BEST_2_MAN",longshot=False)
        if best2: out.append(best2)
        best3=self._best(eligible,3,"BEST_3_MAN",longshot=False)
        if best3: out.append(best3)
        # Long shots remain integrity-qualified; choose from secondary/lower-probability eligible candidates,
        # not WATCH/NO_BET.
        long_pool=sorted(eligible,key=lambda c:c.prediction.final_hr_probability)
        long2=self._best(long_pool[:max(6,len(long_pool)//2)],2,"LONG_SHOT_2_MAN",longshot=True)
        if long2: out.append(long2)
        long3=self._best(long_pool[:max(7,len(long_pool)//2)],3,"LONG_SHOT_3_MAN",longshot=True)
        if long3: out.append(long3)
        return out

    def _best(self,cards:list[PredictionCard],n:int,kind:str,longshot:bool)->Combination|None:
        if len(cards)<n:return None
        best=None;best_score=-1.0
        for combo in combinations(cards,n):
            # Never force an uncertain secondary third leg into BEST_3.
            if not longshot and n==3 and sum(1 for c in combo if c.prediction.classification==ModelClassification.PRIMARY)<1:
                continue
            probs=[c.prediction.final_hr_probability for c in combo]
            joint=math.prod(probs)
            conf=math.prod(max(c.prediction.confidence_score/100.0,0.05) for c in combo)**(1/n)
            shared_games=len({c.prediction.game_pk for c in combo})
            shared_penalty=0.88 if shared_games<n else 1.0
            robustness=100*conf*shared_penalty
            if longshot:
                score=joint*conf*1.05
            else:
                score=joint*conf*shared_penalty
            if score>best_score:
                estimated=1.0
                odds_available=True
                for c in combo:
                    if c.market.quote is None or c.market.quote.decimal_odds is None:
                        odds_available=False;break
                    estimated*=c.market.quote.decimal_odds
                legs=[CombinationLeg(c.prediction.prediction_id,c.prediction.player.player_id,c.prediction.player.full_name,c.prediction.final_hr_probability,c.prediction.classification,c.prediction.game_pk) for c in combo]
                warnings=[]
                if shared_games<n:warnings.append("SHARED_GAME_UNCERTAINTY")
                best=Combination(str(uuid4()),kind,legs,joint,robustness,None,estimated if odds_available else None,warnings)
                best_score=score
        return best
