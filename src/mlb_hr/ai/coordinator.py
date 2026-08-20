from __future__ import annotations

from mlb_hr.ai.providers import AIProvider, AIReview


class AutoFreeAI:
    """Try configured providers in order; no provider is mandatory."""
    def __init__(self,providers:list[AIProvider]|None=None)->None:
        self.providers=providers or []

    def review(self,role:str,payload:dict)->AIReview:
        errors=[]
        for p in self.providers:
            result=p.review(role,payload)
            if result.available:return result
            errors.append(f"{getattr(p,'name','provider')}: {result.error}")
        return AIReview(False,"AUTO_FREE","",role,error="; ".join(errors) if errors else "No AI providers configured")
