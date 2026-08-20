from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from training.bootstrap import bootstrap_statcast
from training.dataset import build_training_table
from training.pipeline import freeze_candidate,run_holdout_2025,validate
from training.release_review import finalize_release


def _date(v:str)->date:return date.fromisoformat(v)

def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="python -m training.cli",description="Offline training/validation pipeline. Never used by production inference.")
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("bootstrap-statcast");a.add_argument("--parquet-dir",type=Path,required=True);a.add_argument("--start",type=_date,required=True);a.add_argument("--end",type=_date,required=True)
    a=sub.add_parser("build-training-table");a.add_argument("--parquet-glob",required=True);a.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("validate");a.add_argument("--training-table",type=Path,required=True);a.add_argument("--output-dir",type=Path,required=True)
    a=sub.add_parser("freeze-candidate");a.add_argument("--training-table",type=Path,required=True);a.add_argument("--validation-dir",type=Path,required=True);a.add_argument("--candidate-dir",type=Path,required=True)
    a=sub.add_parser("run-holdout-2025");a.add_argument("--training-table",type=Path,required=True);a.add_argument("--candidate-dir",type=Path,required=True);a.add_argument("--output-dir",type=Path,required=True)
    a=sub.add_parser("finalize-release");a.add_argument("--reviewed-package",type=Path,required=True);a.add_argument("--macos-report",type=Path,required=True);a.add_argument("--windows-report",type=Path,required=True);a.add_argument("--output-dir",type=Path,required=True)
    return p

def main()->int:
    a=parser().parse_args()
    if a.cmd=="bootstrap-statcast":result=bootstrap_statcast(a.parquet_dir,a.start,a.end)
    elif a.cmd=="build-training-table":result={"training_table":str(build_training_table(a.parquet_glob,a.output))}
    elif a.cmd=="validate":result=validate(a.training_table,a.output_dir)
    elif a.cmd=="freeze-candidate":result=freeze_candidate(a.training_table,a.validation_dir,a.candidate_dir)
    elif a.cmd=="run-holdout-2025":result=run_holdout_2025(a.training_table,a.candidate_dir,a.output_dir)
    else:result=finalize_release(a.reviewed_package,a.macos_report,a.windows_report,a.output_dir)
    print(json.dumps(result,indent=2,default=str));return 0

if __name__=="__main__":raise SystemExit(main())
