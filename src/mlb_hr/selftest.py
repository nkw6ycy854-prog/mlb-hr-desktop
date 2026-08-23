from __future__ import annotations

from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile

from mlb_hr.resources_runtime import bundled_model_text, packaged_migrations_dir
from mlb_hr.storage.paths import resolve_app_paths


def runtime_statcast_status()->dict:
    paths=resolve_app_paths()
    files=list(paths.parquet_dir.glob("season=*/month=*/statcast_*.parquet"))
    return {
        "available":bool(files),
        "parquet_count":len(files),
        "parquet_dir":str(paths.parquet_dir),
    }


def run_self_test(*,require_runtime_data:bool=False)->dict:
    checks={}
    details={}
    checks['python_runtime']=sys.version_info[:2]==(3,13)
    try:
        import PySide6  # noqa: F401
        from PySide6.QtWidgets import QApplication  # noqa: F401
        checks['pyside6_import']=True
    except Exception as exc:
        checks['pyside6_import']=False;details['pyside6_error']=str(exc)
    try:
        import duckdb  # noqa: F401
        checks['duckdb_import']=True
    except Exception as exc:
        checks['duckdb_import']=False;details['duckdb_error']=str(exc)
    try:
        import keyring  # noqa: F401
        checks['keyring_import']=True
    except Exception as exc:
        checks['keyring_import']=False;details['keyring_error']=str(exc)
    try:
        from mlb_hr.storage.sqlite import SQLiteStore
        with tempfile.TemporaryDirectory() as td, packaged_migrations_dir() as migrations:
            st=SQLiteStore(Path(td)/'selftest.db',migrations);st.migrate();st.set_state('selftest',{'ok':True})
            checks['sqlite_migration']=st.get_state('selftest',{}).get('ok') is True
    except Exception as exc:
        checks['sqlite_migration']=False;details['sqlite_error']=str(exc)
    try:
        from mlb_hr.model.package import ModelPackage
        with tempfile.TemporaryDirectory() as td:
            model_dir=Path(td)/'model';model_dir.mkdir();(model_dir/'model_manifest.json').write_text(bundled_model_text(),encoding='utf-8')
            pkg=ModelPackage(model_dir)
            checks['model_package_valid']=bool(pkg.package_hash)
            details['bundled_model_hash']=pkg.package_hash
            details['bundled_model_version']=pkg.manifest.model_version
            details['bundled_model_release_ready']=pkg.release_ready
            details['bundled_model_predictive_ready']=bool(pkg.manifest.metadata.get('predictive_release_ready'))
    except Exception as exc:
        checks['model_package_valid']=False;details['model_error']=str(exc)
    try:
        from mlb_hr.domain.enums import DataFreshness
        from mlb_hr.domain.math import american_to_decimal,decimal_to_implied
        from mlb_hr.domain.models import OddsQuote
        from mlb_hr.odds.market import MarketLayer
        p=.25;now=datetime.now(timezone.utc)
        def quote(a:int):
            d=american_to_decimal(a);return OddsQuote(1,1,'FanDuel','batter_home_runs',a,d,decimal_to_implied(d),now,now,DataFreshness.FRESH,'SELFTEST')
        one=MarketLayer().evaluate(p,quote(500),10);two=MarketLayer().evaluate(p,quote(150),10)
        checks['odds_isolation']=p==.25 and one.edge_pp!=two.edge_pp and one.label!=two.label
    except Exception as exc:
        checks['odds_isolation']=False;details['odds_error']=str(exc)
    try:
        from mlb_hr.postgame.engine import PostgameEngine
        checks['postgame_import']=PostgameEngine is not None
    except Exception as exc:
        checks['postgame_import']=False;details['postgame_error']=str(exc)
    try:
        runtime_data=runtime_statcast_status()
        details['runtime_statcast']=runtime_data
        if require_runtime_data:
            checks['statcast_runtime_available']=bool(runtime_data['available'])
    except Exception as exc:
        details['runtime_statcast_error']=str(exc)
        if require_runtime_data:
            checks['statcast_runtime_available']=False
    result={'created_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'details':details,'passed':all(checks.values())}
    return result


def main()->int:
    result=run_self_test(require_runtime_data='--require-runtime-data' in sys.argv);print(json.dumps(result,indent=2,sort_keys=True));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
