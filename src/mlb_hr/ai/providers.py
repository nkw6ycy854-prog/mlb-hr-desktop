from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from mlb_hr.providers.http_client import HttpClient


@dataclass(slots=True)
class AIReview:
    available: bool
    provider: str
    model: str
    role: str
    verdict: str = "UNAVAILABLE"
    reasons: list[str] | None = None
    raw: dict[str, Any] | None = None
    error: str | None = None


class AIProvider(Protocol):
    name: str
    def review(self, role: str, payload: dict[str, Any]) -> AIReview: ...


class DisabledAIProvider:
    name="disabled"
    def review(self, role:str,payload:dict[str,Any])->AIReview:
        return AIReview(False,self.name,"",role,error="AI provider not configured")


class OpenAICompatibleProvider:
    def __init__(self, *, name:str, endpoint:str, api_key:str, model:str, http:HttpClient|None=None, extra_headers:dict[str,str]|None=None) -> None:
        self.name=name;self.endpoint=endpoint;self.api_key=api_key;self.model=model;self.http=http or HttpClient();self.extra_headers=extra_headers or {}
    def review(self,role:str,payload:dict[str,Any])->AIReview:
        if not self.api_key or not self.model:
            return AIReview(False,self.name,self.model,role,error="Missing API key/model")
        schema_instruction=(
            "Return JSON only with keys verdict (PASS|CAUTION|REJECT) and reasons (array of short strings). "
            "You are a reviewer. Do not create or alter a numeric HR probability."
        )
        body={"model":self.model,"temperature":0,"response_format":{"type":"json_object"},"messages":[
            {"role":"system","content":schema_instruction},
            {"role":"user","content":json.dumps({"role":role,"snapshot":payload},default=str)}]}
        headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json",**self.extra_headers}
        try:
            # HttpClient intentionally only exposes GET for data providers; AI writes are kept isolated and bounded here.
            import httpx
            with httpx.Client(timeout=20.0,headers=headers) as c:
                r=c.post(self.endpoint,json=body);r.raise_for_status();data=r.json()
            text=data["choices"][0]["message"]["content"]
            parsed=json.loads(text) if isinstance(text,str) else text
            verdict=str(parsed.get("verdict","CAUTION")).upper()
            if verdict not in {"PASS","CAUTION","REJECT"}:verdict="CAUTION"
            return AIReview(True,self.name,self.model,role,verdict,list(parsed.get("reasons") or []),data)
        except Exception as exc:
            return AIReview(False,self.name,self.model,role,error=str(exc))


class GeminiProvider:
    name="gemini"
    def __init__(self,api_key:str,model:str,http:HttpClient|None=None)->None:
        self.api_key=api_key;self.model=model;self.http=http or HttpClient()
    def review(self,role:str,payload:dict[str,Any])->AIReview:
        if not self.api_key or not self.model:return AIReview(False,self.name,self.model,role,error="Missing API key/model")
        endpoint=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        prompt="Return JSON only: {verdict: PASS|CAUTION|REJECT, reasons:[...]}. Never alter HR probability. Review this snapshot: "+json.dumps({"role":role,"snapshot":payload},default=str)
        try:
            import httpx
            with httpx.Client(timeout=20.0) as c:
                r=c.post(endpoint,params={"key":self.api_key},json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0,"responseMimeType":"application/json"}});r.raise_for_status();data=r.json()
            text=data["candidates"][0]["content"]["parts"][0]["text"]
            parsed=json.loads(text);verdict=str(parsed.get("verdict","CAUTION")).upper()
            if verdict not in {"PASS","CAUTION","REJECT"}:verdict="CAUTION"
            return AIReview(True,self.name,self.model,role,verdict,list(parsed.get("reasons") or []),data)
        except Exception as exc:return AIReview(False,self.name,self.model,role,error=str(exc))


class OllamaProvider:
    name="ollama"
    def __init__(self,model:str,endpoint:str="http://127.0.0.1:11434/api/chat")->None:
        self.model=model;self.endpoint=endpoint
    def review(self,role:str,payload:dict[str,Any])->AIReview:
        if not self.model:return AIReview(False,self.name,"",role,error="No local model configured")
        try:
            import httpx
            prompt="JSON only with verdict PASS|CAUTION|REJECT and reasons. Do not alter HR probability. "+json.dumps({"role":role,"snapshot":payload},default=str)
            with httpx.Client(timeout=45.0) as c:
                r=c.post(self.endpoint,json={"model":self.model,"stream":False,"format":"json","messages":[{"role":"user","content":prompt}]});r.raise_for_status();data=r.json()
            parsed=json.loads(data["message"]["content"]);v=str(parsed.get("verdict","CAUTION")).upper()
            if v not in {"PASS","CAUTION","REJECT"}:v="CAUTION"
            return AIReview(True,self.name,self.model,role,v,list(parsed.get("reasons") or []),data)
        except Exception as exc:return AIReview(False,self.name,self.model,role,error=str(exc))
