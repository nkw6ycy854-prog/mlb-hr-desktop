from __future__ import annotations

from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np

from mlb_hr.calibration.engine import CalibrationEngine
from training.features import CORE_FEATURES,DEFAULT_K,lineup_pa_distributions
from training.metrics import metric_bundle
from training.modeling import (
    ablation_report, derive_gate_support, fit_final, read_training_table, select_calibration,
    select_probability_thresholds, validation_tolerances, walk_forward, _build_validation_games,
)


def _json(path:Path,obj)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(obj,indent=2,sort_keys=True,default=str),encoding="utf-8");tmp.replace(path)


def validate(training_table:Path,output_dir:Path)->dict:
    df=read_training_table(training_table);arts,oof=walk_forward(df,CORE_FEATURES)
    calibration,oof_cal,cal_report=select_calibration(oof)
    thresholds=select_probability_thresholds(oof_cal);thresholds.update(derive_gate_support(oof_cal,thresholds))
    tolerances=validation_tolerances(oof_cal)
    folds={str(a.validation_year):a.metrics for a in arts}
    ablation=ablation_report(df)
    report={
        "created_at":datetime.now(timezone.utc).isoformat(),"features":CORE_FEATURES,"folds":folds,
        "calibration":cal_report,"selected_calibration":calibration,"thresholds":thresholds,
        "holdout_tolerances":tolerances,"ablation":ablation,
    }
    _json(output_dir/"validation_report.json",report)
    # OOF is development evidence and safe to persist for threshold/audit work.
    try:
        import duckdb
        con=duckdb.connect(database=":memory:");con.register("oof",oof_cal);con.execute("COPY oof TO ? (FORMAT PARQUET,COMPRESSION ZSTD)",[str(output_dir/"oof_validation.parquet")]);con.close()
    except Exception:
        oof_cal.to_csv(output_dir/"oof_validation.csv",index=False)
    return report


def freeze_candidate(training_table:Path,validation_dir:Path,candidate_dir:Path)->dict:
    report=json.loads((validation_dir/"validation_report.json").read_text())
    if report["thresholds"].get("threshold_support_failed"):
        raise RuntimeError("Validation did not produce enough stable threshold support; candidate cannot be frozen")
    df=read_training_table(training_table);train=df[df["game_date"].dt.year<=2024]
    scaler,model=fit_final(df,CORE_FEATURES)
    pa_dists=lineup_pa_distributions(train)
    manifest={
        "model_version":"V1-CANDIDATE-2","feature_version":"FEATURES-V1-CANDIDATE-2",
        "calibration_version":"CAL-V1-CANDIDATE-2","quality_gate_version":"QG-V1-CANDIDATE-2",
        "model_type":"logistic_per_pa","release_ready":False,"training_cutoff":"2024-12-31",
        "validation_periods":["2019-2021->2022","2019-2022->2023","2019-2023->2024"],
        "holdout_period":"2025_LOCKED_NOT_RUN","feature_names":CORE_FEATURES,
        "feature_means":{f:float(v) for f,v in zip(CORE_FEATURES,scaler.mean_)},
        "feature_scales":{f:float(v if v else 1) for f,v in zip(CORE_FEATURES,scaler.scale_)},
        "coefficients":{f:float(v) for f,v in zip(CORE_FEATURES,model.coef_[0])},"intercept":float(model.intercept_[0]),
        "calibration":report["selected_calibration"],"thresholds":report["thresholds"],
        "uncertainty":{"scenario_draws":600,"feature_noise_scale":0.15,"bullpen_adjustment_scale":0.0,"confidence_floor":5},
        "versions":{"ZONE_VERSION":"NOT_IN_V1_CANDIDATE","SIMILAR_PITCHER_VERSION":"NOT_IN_V1_CANDIDATE","PARK_VERSION":"STRUCTURE_IMPLEMENTED_NOT_VALIDATED","PA_VERSION":"PA-DIST-V1-CANDIDATE","STARTER_EXPOSURE_VERSION":"SPX-EMPIRICAL-V1","BULLPEN_VERSION":"BP-NEUTRAL-BATTER-BASELINE-V1","GAME_PROBABILITY_VERSION":"GAME-HR-SPX-V2","UNCERTAINTY_VERSION":"UNC-V1-STRUCTURE"},
        "deterministic_seed":20260817,"package_hash":"",
        "metadata":{"release_status":"CANDIDATE_FROZEN_AWAITING_2025_HOLDOUT","validation_report_hash":"","game_probability_policy":{"starter_matchup":"model_per_pa","post_starter_fallback":"batter_hr_pa","individual_bullpen_adjustment":"DISABLED_UNTIL_OOS_VALIDATED"},"feature_config":{"home_ninth_shift":0.0,"reliability":{"batter_pa_k":DEFAULT_K["batter_pa"],"batter_bbe_k":DEFAULT_K["batter_bbe"],"pitcher_bf_k":DEFAULT_K["pitcher_bf"],"pitcher_bbe_k":DEFAULT_K["pitcher_bbe"],"bvp_pa_k":60,"split_pa_k":DEFAULT_K["split"]},"player_survival_default":1.0,"starter_exposure":{"league_starter_bf_prior":18.5,"starter_bf_shrink_k":8,"starter_survival_scale":3.4},"park":{"temperature_per_10f":0.0,"wind_out_per_10mph":0.0,"humidity_per_20pct":0.0,"weather_cap":0.12,"park_factors":{}},"bullpen":{},"pa_distribution_by_slot":pa_dists},"holdout_tolerances":report["holdout_tolerances"],"excluded_unvalidated_modules":["pitch_type_match","velocity_match","zone_match","similar_pitcher_delta","bvp_delta","park_delta","weather_index","profile_change_score"]}
    }
    vh=hashlib.sha256((validation_dir/"validation_report.json").read_bytes()).hexdigest();manifest["metadata"]["validation_report_hash"]=vh
    candidate_dir.mkdir(parents=True,exist_ok=True);_json(candidate_dir/"model_manifest.json",manifest)
    canonical=json.dumps({**manifest,"package_hash":""},sort_keys=True,separators=(",",":"),default=str).encode();h=hashlib.sha256(canonical).hexdigest();manifest["package_hash"]=h;_json(candidate_dir/"model_manifest.json",manifest)
    _json(candidate_dir/"candidate_lock.json",{"locked_at":datetime.now(timezone.utc).isoformat(),"package_hash":h,"holdout":"2025","opened":False})
    return manifest


def run_holdout_2025(training_table:Path,candidate_dir:Path,output_dir:Path)->dict:
    lock_path=candidate_dir/"candidate_lock.json";lock=json.loads(lock_path.read_text())
    if lock.get("opened"):
        raise RuntimeError("2025 holdout was already opened for this candidate. Refusing a second official run.")
    manifest=json.loads((candidate_dir/"model_manifest.json").read_text());expected=lock["package_hash"]
    if manifest.get("package_hash")!=expected:raise RuntimeError("Candidate package changed after lock")
    lock["opened"]=True;lock["opened_at"]=datetime.now(timezone.utc).isoformat();_json(lock_path,lock)
    df=read_training_table(training_table);train=df[df["game_date"].dt.year<=2024];test=df[df["game_date"].dt.year==2025]
    if test.empty:raise RuntimeError("No 2025 observations found")
    # Recreate frozen model from manifest, never refit after holdout is opened.
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    class FrozenScaler:
        mean_=np.array([manifest["feature_means"][f] for f in CORE_FEATURES]);scale_=np.array([manifest["feature_scales"][f] for f in CORE_FEATURES])
        def transform(self,x):return (np.asarray(x,float)-self.mean_)/self.scale_
    class FrozenModel:
        coef_=np.array([[manifest["coefficients"][f] for f in CORE_FEATURES]]);intercept_=np.array([manifest["intercept"]])
        def predict_proba(self,x):
            z=np.asarray(x,float)@self.coef_[0]+self.intercept_[0];p=1/(1+np.exp(-z));return np.column_stack([1-p,p])
    games=_build_validation_games(train,test,CORE_FEATURES,FrozenScaler(),FrozenModel())
    cal=CalibrationEngine(manifest["calibration"]);games["p_full"]=games["p_full_raw"].map(cal.calibrate)
    metrics={name:metric_bundle(games["actual_hr"],games["p_full"] if name=="full" else games[f"p_{name}_raw"]) for name in ["full","a","b","c"]}
    tol=manifest["metadata"]["holdout_tolerances"]
    blockers=[]
    if metrics["full"]["brier"]>float(tol["max_holdout_brier"]):blockers.append("HOLDOUT_BRIER_DEGRADATION")
    if metrics["full"]["ece"]>float(tol["max_holdout_ece"]):blockers.append("HOLDOUT_CALIBRATION_FAIL")
    if metrics["full"]["monotonicity"]<float(tol["min_holdout_monotonicity"]):blockers.append("HOLDOUT_ORDERING_FAIL")
    for base in ["a","b","c"]:
        if metrics["full"]["brier"]>=metrics[base]["brier"]:blockers.append(f"BASELINE_{base.upper()}_NOT_BEATEN")
    passed=not blockers
    result={"holdout_run_id":hashlib.sha256(f"{expected}:{lock['opened_at']}".encode()).hexdigest()[:20],"candidate_hash":expected,"run_at":lock["opened_at"],"metrics":metrics,"blockers":blockers,"passed":passed}
    output_dir.mkdir(parents=True,exist_ok=True);_json(output_dir/"holdout_2025_result.json",result)
    manifest["holdout_period"]="2025_OFFICIAL_RUN_COMPLETE";manifest["metadata"]["holdout_result"]=result
    manifest["release_ready"]=False
    if passed:
        manifest["metadata"]["predictive_release_ready"]=True
        manifest["metadata"]["release_status"]="PREDICTIVE_RELEASE_READY_PENDING_NATIVE_BUILD_TESTS"
    else:
        manifest["metadata"]["predictive_release_ready"]=False
        manifest["metadata"]["release_status"]="REJECTED_HOLDOUT_FAIL"
    # Do not overwrite the frozen candidate: create a separate reviewed package.
    reviewed=output_dir/("V1.0.0_predictive" if passed else "rejected_candidate")
    reviewed.mkdir(parents=True,exist_ok=True);manifest["package_hash"]="";canonical=json.dumps(manifest,sort_keys=True,separators=(",",":"),default=str).encode();manifest["package_hash"]=hashlib.sha256(canonical).hexdigest();_json(reviewed/"model_manifest.json",manifest)
    return result
