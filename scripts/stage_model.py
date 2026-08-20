from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from mlb_hr.model.package import ModelPackage


def main()->int:
    p=argparse.ArgumentParser(description='Stage a frozen model package into the native app resources before packaging.')
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--allow-development',action='store_true')
    a=p.parse_args()
    pkg=ModelPackage(a.model_dir)
    predictive_ready=bool(pkg.manifest.metadata.get('predictive_release_ready'))
    if not (pkg.release_ready or predictive_ready or a.allow_development):
        raise SystemExit('Refusing to stage an unreviewed model. Use --allow-development only for a dev build.')
    dest=ROOT/'src'/'mlb_hr'/'resources'/'bundled_model'/'model_manifest.json'
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix('.json.tmp')
    shutil.copy2(a.model_dir/'model_manifest.json',tmp);tmp.replace(dest)
    print(json.dumps({'staged':str(a.model_dir),'model_version':pkg.manifest.model_version,'package_hash':pkg.package_hash,'release_ready':pkg.release_ready,'predictive_release_ready':predictive_ready},indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
