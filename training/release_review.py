from __future__ import annotations

from datetime import datetime,timezone
import hashlib,json
from pathlib import Path

HARD_NATIVE_KEYS={
    "platform_correct","standalone_artifact_exists","artifact_executable_exists","artifact_self_test_pass",
    "python_runtime","pyside6_import","duckdb_import","keyring_import","sqlite_migration",
    "model_package_valid","odds_isolation","postgame_import","expected_model_hash",
}


def _load(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8"))
def _write(path:Path,obj:dict)->None:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,sort_keys=True,default=str),encoding="utf-8")

def finalize_release(reviewed_package:Path,macos_report:Path,windows_report:Path,output_dir:Path)->dict:
    manifest=_load(reviewed_package/"model_manifest.json")
    blockers=[]
    if not manifest.get("metadata",{}).get("predictive_release_ready"):blockers.append("PREDICTIVE_RELEASE_NOT_READY")
    expected_hash=str(manifest.get("package_hash") or "")
    for label,path in [("MACOS",macos_report),("WINDOWS",windows_report)]:
        report=_load(path)
        expected_platform="Darwin" if label=="MACOS" else "Windows"
        if report.get("platform")!=expected_platform:blockers.append(f"{label}_WRONG_PLATFORM_REPORT")
        checks=report.get("checks",{})
        for key in HARD_NATIVE_KEYS:
            if not checks.get(key,False):blockers.append(f"{label}_{key.upper()}_FAIL")
        observed=str(report.get("details",{}).get("bundled_model_hash") or "")
        if not expected_hash or observed!=expected_hash:blockers.append(f"{label}_MODEL_HASH_MISMATCH")
    passed=not blockers
    result={"reviewed_at":datetime.now(timezone.utc).isoformat(),"passed":passed,"blockers":blockers,"macos_report":str(macos_report),"windows_report":str(windows_report)}
    if passed:
        manifest["release_ready"]=True;manifest["model_version"]="V1.0.0";manifest["metadata"]["release_status"]="V1.0_READY";manifest["metadata"]["release_review"]=result
        manifest["package_hash"]="";raw=json.dumps(manifest,sort_keys=True,separators=(",",":"),default=str).encode();manifest["package_hash"]=hashlib.sha256(raw).hexdigest()
        output_dir.mkdir(parents=True,exist_ok=True);_write(output_dir/"model_manifest.json",manifest)
    _write(output_dir.parent/"release_review.json",result)
    return result
