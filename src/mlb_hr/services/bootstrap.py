from __future__ import annotations

import json

from mlb_hr.ai.coordinator import AutoFreeAI
from mlb_hr.ai.providers import GeminiProvider, OllamaProvider, OpenAICompatibleProvider
from mlb_hr.model.package import ModelPackage
from mlb_hr.providers.odds import OddsProvider
from mlb_hr.providers.secrets import SecretStore
from mlb_hr.services.analysis import AnalysisService
from mlb_hr.resources_runtime import bundled_model_text, packaged_migrations_dir
from mlb_hr.storage.analytics import AnalyticsStore
from mlb_hr.storage.paths import AppPaths, resolve_app_paths
from mlb_hr.storage.sqlite import SQLiteStore


def _semantic_version(value:str)->tuple[int,int,int]:
    import re
    m=re.fullmatch(r"V?(\d+)\.(\d+)\.(\d+)",str(value or ""))
    return tuple(map(int,m.groups())) if m else (0,0,0)

def ensure_default_model(paths:AppPaths):
    configured=paths.model_dir/"active"
    manifest=configured/"model_manifest.json"
    configured.mkdir(parents=True,exist_ok=True)
    # The bundled package is staged at native build time. A release install may promote
    # a newer approved bundled model, but never downgrade an existing approved package
    # to a development/candidate package.
    raw=bundled_model_text();bundled=json.loads(raw)
    replace_active=not manifest.exists()
    if manifest.exists():
        try:
            current=json.loads(manifest.read_text(encoding="utf-8"))
            bundled_ready=bool(bundled.get("release_ready"));current_ready=bool(current.get("release_ready"))
            if bundled_ready and (not current_ready or _semantic_version(bundled.get("model_version",""))>_semantic_version(current.get("model_version",""))):
                replace_active=True
        except Exception:
            # A corrupt active manifest is recoverable from the installed bundled package.
            replace_active=True
    if replace_active:
        tmp=manifest.with_suffix(".json.tmp");tmp.write_text(raw,encoding="utf-8");tmp.replace(manifest)
    return configured


def build_services(*,demo:bool=False)->tuple[AnalysisService,AppPaths,SQLiteStore]:
    paths=resolve_app_paths()
    with packaged_migrations_dir() as migration_dir:
        store=SQLiteStore(paths.db_path,migration_dir);store.migrate()
    analytics=AnalyticsStore(paths.parquet_dir)
    package=ModelPackage(ensure_default_model(paths))
    secrets=SecretStore();odds_key=secrets.get("THE_ODDS_API_KEY")
    odds=OddsProvider(odds_key) if odds_key else None
    ai_providers=[]
    groq_key=secrets.get("GROQ_API_KEY");groq_model=str(store.get_state("groq_model","") or "").strip()
    if groq_key and groq_model:
        ai_providers.append(OpenAICompatibleProvider(name="groq",endpoint="https://api.groq.com/openai/v1/chat/completions",api_key=groq_key,model=groq_model))
    gemini_key=secrets.get("GEMINI_API_KEY");gemini_model=str(store.get_state("gemini_model","") or "").strip()
    if gemini_key and gemini_model:
        ai_providers.append(GeminiProvider(gemini_key,gemini_model))
    openrouter_key=secrets.get("OPENROUTER_API_KEY");openrouter_model=str(store.get_state("openrouter_model","") or "").strip()
    if openrouter_key and openrouter_model:
        ai_providers.append(OpenAICompatibleProvider(name="openrouter",endpoint="https://openrouter.ai/api/v1/chat/completions",api_key=openrouter_key,model=openrouter_model))
    ollama_model=str(store.get_state("ollama_model","") or "").strip()
    if ollama_model:ai_providers.append(OllamaProvider(ollama_model))
    ai_review_enabled=bool(store.get_state("ai_review_enabled",False))
    ai=AutoFreeAI(ai_providers) if (ai_providers and ai_review_enabled) else None
    stake=float(store.get_state("default_stake",10.0))
    service=AnalysisService(store=store,analytics=analytics,model_package=package,odds=odds,ai=ai,stake=stake,allow_unvalidated_demo=demo)
    return service,paths,store
