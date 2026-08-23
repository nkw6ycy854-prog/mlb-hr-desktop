from __future__ import annotations

import argparse
import json
import platform
import plistlib
from pathlib import Path
import subprocess
from datetime import datetime,timezone


def _artifact_executable(artifact:Path)->Path:
    if platform.system()=='Darwin':
        if not artifact.is_dir():raise RuntimeError('macOS artifact must be a .app directory')
        info=artifact/'Contents'/'Info.plist'
        if not info.exists():raise RuntimeError('Missing Contents/Info.plist')
        data=plistlib.loads(info.read_bytes());name=data.get('CFBundleExecutable')
        if not name:raise RuntimeError('Missing CFBundleExecutable')
        return artifact/'Contents'/'MacOS'/str(name)
    if platform.system()=='Windows':
        if not artifact.is_file():raise RuntimeError('Windows artifact must be an .exe file')
        return artifact
    raise RuntimeError('Native smoke must run on Darwin or Windows')


def main()->int:
    p=argparse.ArgumentParser(description='Run hard native smoke checks against the packaged artifact itself.')
    p.add_argument('--artifact',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-model-hash',default='')
    p.add_argument('--require-runtime-data',action='store_true')
    a=p.parse_args()
    checks={'platform_correct':platform.system() in {'Darwin','Windows'},'standalone_artifact_exists':a.artifact.exists()}
    details={}
    try:
        exe=_artifact_executable(a.artifact);checks['artifact_executable_exists']=exe.exists();details['executable']=str(exe)
        cmd=[str(exe),'--self-test']
        if a.require_runtime_data:cmd.append('--require-runtime-data')
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=90,check=False)
        details['self_test_returncode']=cp.returncode;details['self_test_stderr']=cp.stderr[-4000:]
        payload=json.loads(cp.stdout.strip())
        details['artifact_self_test']=payload
        checks['artifact_self_test_pass']=cp.returncode==0 and bool(payload.get('passed'))
        for key,value in (payload.get('checks') or {}).items():checks[key]=bool(value)
        bundled_hash=str((payload.get('details') or {}).get('bundled_model_hash') or '')
        details['bundled_model_hash']=bundled_hash
        checks['expected_model_hash']=True if not a.expected_model_hash else bundled_hash==a.expected_model_hash
    except Exception as exc:
        checks['artifact_executable_exists']=False;checks['artifact_self_test_pass']=False;checks['expected_model_hash']=False;details['error']=str(exc)
    report={'platform':platform.system(),'created_at':datetime.now(timezone.utc).isoformat(),'artifact':str(a.artifact),'expected_model_hash':a.expected_model_hash,'checks':checks,'details':details,'passed':all(checks.values())}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
