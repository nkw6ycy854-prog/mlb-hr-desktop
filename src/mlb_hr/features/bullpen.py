from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


@dataclass(slots=True)
class BullpenComponent:
    weighted_hr_bf: float
    r_hand_probability: float
    l_hand_probability: float
    reliability: float
    depletion_score: float
    mixture_entropy: float
    likely_relief_distribution: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BullpenEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    def evaluate(self, candidates: list[dict[str, Any]], league_hr_bf: float) -> BullpenComponent:
        if not candidates:
            return BullpenComponent(
                weighted_hr_bf=league_hr_bf,
                r_hand_probability=0.72,
                l_hand_probability=0.28,
                reliability=0.20,
                depletion_score=50.0,
                mixture_entropy=1.0,
                warnings=["Bullpen específico no disponible; se usa prior de liga."],
            )
        weights=[]
        total_recent=0.0
        for c in candidates:
            # Workload primarily affects availability, not pitcher quality.
            workload = float(c.get("pitches_1d",0))*0.018 + float(c.get("pitches_2d",0))*0.008 + max(0,int(c.get("apps_2d",0))-1)*0.12
            availability=max(0.05,min(1.0,1.0-workload))
            entry=float(c.get("avg_entry_inning",6.0) or 6.0)
            # Pregame marginal role weight; avoids assuming closer is certain.
            role_weight=1.0
            if entry>=8: role_weight=0.85
            elif entry<=4: role_weight=0.70
            multi=1.0+min(float(c.get("avg_bf",3.0)),9.0)/12.0
            w=availability*role_weight*multi*math.sqrt(max(float(c.get("relief_apps",1)),1.0))
            weights.append(w)
            total_recent += float(c.get("pitches_3d",0))
        norm=sum(weights) or 1.0
        probs=[w/norm for w in weights]
        hr=sum(p*float(c.get("hr_bf",league_hr_bf) or league_hr_bf) for p,c in zip(probs,candidates))
        r=sum(p for p,c in zip(probs,candidates) if str(c.get("hand","R")).upper()=="R")
        l=1.0-r
        entropy=-sum(p*math.log(max(p,1e-12)) for p in probs)
        max_entropy=math.log(max(len(probs),1)) if len(probs)>1 else 1.0
        entropy_norm=entropy/max_entropy if max_entropy else 0.0
        sample=sum(int(c.get("relief_apps",0)) for c in candidates)
        rel=min(0.90, 0.25+0.65*(sample/(sample+40.0)))*(1.0-0.25*entropy_norm)
        depletion=max(0.0,min(100.0,total_recent/max(len(candidates),1)*2.0))
        ranked=sorted(
            [
                {
                    "pitcher_id":int(c["pitcher_id"]),
                    "hand":c.get("hand","R"),
                    "probability":p,
                    "availability_weight":w,
                }
                for c,p,w in zip(candidates,probs,weights)
            ],
            key=lambda x:x["probability"], reverse=True,
        )
        return BullpenComponent(hr,r,l,rel,depletion,entropy_norm,ranked[:8],[])
