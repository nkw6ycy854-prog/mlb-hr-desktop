from mlb_hr.ai.coordinator import AutoFreeAI
from mlb_hr.ai.providers import AIReview


class FakeProvider:
    def __init__(self,name,available,verdict="PASS"):
        self.name=name;self.available=available;self.verdict=verdict
    def review(self,role,payload):
        return AIReview(self.available,self.name,"fake-model",role,self.verdict,["checked"] if self.available else None,error=None if self.available else "offline")


def test_auto_free_ai_falls_back_without_touching_probability_payload():
    payload={"final_hr_probability":0.231,"feature_values":{"x":1.0}}
    original=dict(payload)
    ai=AutoFreeAI([FakeProvider("first",False),FakeProvider("second",True,"CAUTION")])
    result=ai.review("MODEL_CRITIC",payload)
    assert result.available is True
    assert result.provider=="second"
    assert result.verdict=="CAUTION"
    assert payload==original
