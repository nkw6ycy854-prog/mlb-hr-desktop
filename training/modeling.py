from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from mlb_hr.domain.math import clamp
from mlb_hr.features.exposure import StarterExposureEngine
from training.features import CORE_FEATURES, FEATURE_GROUPS, game_rows, lineup_pa_distributions, transform_raw_features
from training.metrics import brier, ece, metric_bundle

FOLDS=[(2021,2022),(2022,2023),(2023,2024)]

@dataclass
class FoldArtifact:
    validation_year:int
    predictions:pd.DataFrame
    metrics:dict[str,Any]
    coefficients:dict[str,float]
    intercept:float
    means:dict[str,float]
    scales:dict[str,float]


def read_training_table(path:Path)->pd.DataFrame:
    try:import duckdb
    except Exception as exc:raise RuntimeError("DuckDB is required to read the training table") from exc
    con=duckdb.connect(database=":memory:")
    df=con.execute("SELECT * FROM read_parquet(?)",[str(path)]).df();con.close()
    df["game_date"]=pd.to_datetime(df["game_date"])
    return transform_raw_features(df)


def _fit_per_pa(train:pd.DataFrame, features:list[str])->tuple[StandardScaler,LogisticRegression]:
    x=train[features].replace([np.inf,-np.inf],np.nan).fillna(train[features].median(numeric_only=True)).fillna(0.0)
    y=train["label_hr"].astype(int)
    scaler=StandardScaler().fit(x)
    model=LogisticRegression(C=1.0,max_iter=600,class_weight=None,random_state=20260817).fit(scaler.transform(x),y)
    return scaler,model


def _predict_per_pa(df:pd.DataFrame,features:list[str],scaler:StandardScaler,model:LogisticRegression)->np.ndarray:
    x=df[features].replace([np.inf,-np.inf],np.nan).fillna(0.0)
    return model.predict_proba(scaler.transform(x))[:,1]


def _game_probability(p_pa:float,dist:dict[str,float])->float:
    total=0.0
    for key,w in dist.items():
        n=7 if key=="7" else int(key)
        total+=float(w)*(1.0-(1.0-clamp(float(p_pa),1e-8,.75))**n)
    return clamp(total,1e-8,.95)


def _starter_history(train:pd.DataFrame)->pd.DataFrame:
    """Historical starter workload using training-only data.

    One row per starter-game is reduced to batters faced, then aggregated by pitcher.
    This is strictly pre-validation-period evidence in each walk-forward fold.
    """
    s=train[train["is_starter_pitcher"].astype(bool)].copy()
    starts=(s.groupby(["game_pk","pitcher"],as_index=False)
              .agg(bf=("label_hr","size")))
    if starts.empty:
        return pd.DataFrame(columns=["avg_bf","starts"])
    return starts.groupby("pitcher").agg(avg_bf=("bf","mean"),starts=("bf","size"))


def _exposure_probability(
    p_sp:float,
    p_bp:float,
    dist:dict[str,float],
    exposure,
)->float:
    """Integrate game-HR probability across ordered PA starter/bullpen exposure."""
    total=0.0
    norm=sum(float(v) for v in dist.values()) or 1.0
    for key,w in dist.items():
        n=7 if key=="7" else int(key)
        no_hr=1.0
        for pa_idx in range(1,n+1):
            q=float(exposure.q_by_pa.get(pa_idx,0.0))
            p=q*float(p_sp)+(1.0-q)*float(p_bp)
            no_hr*=1.0-clamp(p,1e-8,.75)
        total+=(float(w)/norm)*(1.0-no_hr)
    return clamp(total,1e-8,.95)


def _league_pa(train:pd.DataFrame)->float:
    den=float(len(train));return float(train["label_hr"].sum()/den) if den else .03


def _build_validation_games(train:pd.DataFrame,val:pd.DataFrame,features:list[str],scaler,model)->pd.DataFrame:
    games=game_rows(val).copy()
    pa_dists=lineup_pa_distributions(train)
    games["p_pa_full"]=_predict_per_pa(games,features,scaler,model)
    league=_league_pa(train)
    games["p_pa_a"]=league
    # Baseline B: batter historical HR/PA (already shrunk and pre-game).  It also
    # serves as the neutral post-starter bullpen fallback in Candidate 2.
    games["p_pa_b"]=games["batter_hr_pa"].clip(.001,.25)
    # Baseline C: simple power + pitcher vulnerability + handedness.
    simple=["batter_hr_pa","batter_barrel_rate","batter_hardhit_rate","pitcher_hr_bf","pitcher_barrel_allowed","pitcher_hardhit_allowed","batter_platoon_delta","pitcher_platoon_delta"]
    sc_c,m_c=_fit_per_pa(train,simple)
    games["p_pa_c"]=_predict_per_pa(games,simple,sc_c,m_c)

    # Candidate 2: starter-specific matchup applies only while the actual starter is
    # expected to remain in the game.  Later PA fall back to the batter's shrunk
    # historical HR/PA until an individual-bullpen model earns OOS support.
    sp_stats=_starter_history(train)
    exposure_engine=StarterExposureEngine({
        "league_starter_bf_prior":18.5,
        "starter_bf_shrink_k":8.0,
        "starter_survival_scale":3.4,
    })

    p_full=[];p_a=[];p_b=[];p_c=[];expected_sp=[];expected_bp=[];sp_rel=[]
    for _,row in games.iterrows():
        dist=pa_dists.get(str(int(row["lineup_slot"]))) or {"4":.5,"5":.5}
        pa_dist={int(k):float(v) for k,v in dist.items()}
        pitcher_id=int(row["pitcher"])
        if pitcher_id in sp_stats.index:
            avg_bf=float(sp_stats.loc[pitcher_id,"avg_bf"]);starts=int(sp_stats.loc[pitcher_id,"starts"])
        else:
            avg_bf=18.5;starts=0
        exposure=exposure_engine.project(int(row["lineup_slot"]),pa_dist,avg_bf,starts)
        p_full.append(_exposure_probability(float(row["p_pa_full"]),float(row["p_pa_b"]),dist,exposure))
        p_c.append(_exposure_probability(float(row["p_pa_c"]),float(row["p_pa_b"]),dist,exposure))
        p_a.append(_game_probability(float(row["p_pa_a"]),dist))
        p_b.append(_game_probability(float(row["p_pa_b"]),dist))
        expected_sp.append(float(exposure.expected_pa_vs_starter));expected_bp.append(float(exposure.expected_pa_vs_bullpen));sp_rel.append(float(exposure.reliability))
    games["p_full_raw"]=p_full;games["p_a_raw"]=p_a;games["p_b_raw"]=p_b;games["p_c_raw"]=p_c
    games["expected_pa_vs_starter"]=expected_sp;games["expected_pa_vs_bullpen"]=expected_bp;games["starter_exposure_reliability"]=sp_rel
    games["year"]=games["game_date"].dt.year
    # Proxy score follows coefficient contribution magnitude, not an invented probability.
    z=(games[features].fillna(0.0).to_numpy()-scaler.mean_)/np.where(scaler.scale_==0,1,scaler.scale_)
    contrib=z*model.coef_[0]
    strength=np.tanh(np.sum(np.maximum(contrib,0),axis=1)/3.0)
    games["matchup_score_proxy"]=50+50*strength
    # OOD formulation mirrors production standardized excess beyond 1.5 SD.
    excess=np.maximum(0,np.abs(z)-1.5)
    rms=np.sqrt(np.mean(excess**2,axis=1))
    games["ood_proxy"]=100*(1-np.exp(-rms/2.0))
    return games


def walk_forward(df:pd.DataFrame,features:list[str]|None=None)->tuple[list[FoldArtifact],pd.DataFrame]:
    features=features or list(CORE_FEATURES)
    artifacts=[];all_preds=[]
    for train_end,val_year in FOLDS:
        train=df[df["game_date"].dt.year<=train_end].copy();val=df[df["game_date"].dt.year==val_year].copy()
        if train.empty or val.empty:raise RuntimeError(f"Missing data for walk-forward fold <= {train_end} -> {val_year}")
        scaler,model=_fit_per_pa(train,features)
        games=_build_validation_games(train,val,features,scaler,model)
        metrics={name:metric_bundle(games["actual_hr"],games[f"p_{name}_raw"]) for name in ["full","a","b","c"]}
        art=FoldArtifact(val_year,games,metrics,{f:float(c) for f,c in zip(features,model.coef_[0])},float(model.intercept_[0]),{f:float(m) for f,m in zip(features,scaler.mean_)},{f:float(v if v else 1) for f,v in zip(features,scaler.scale_)})
        artifacts.append(art);all_preds.append(games)
    return artifacts,pd.concat(all_preds,ignore_index=True)


def _fit_calibrator(method:str,p:np.ndarray,y:np.ndarray):
    p=np.clip(p,1e-6,1-1e-6);y=np.asarray(y,dtype=int)
    if method=="none":return {"method":"none"},lambda x:np.asarray(x,dtype=float)
    if method=="platt":
        x=np.log(p/(1-p)).reshape(-1,1);m=LogisticRegression(C=1e6,max_iter=500,random_state=20260817).fit(x,y)
        cfg={"method":"platt","a":float(m.coef_[0][0]),"b":float(m.intercept_[0])}
        return cfg,lambda q:1/(1+np.exp(-(cfg["a"]*np.log(np.clip(q,1e-6,1-1e-6)/(1-np.clip(q,1e-6,1-1e-6)))+cfg["b"])))
    if method=="isotonic":
        m=IsotonicRegression(y_min=0,y_max=1,out_of_bounds="clip").fit(p,y)
        cfg={"method":"isotonic","x":[float(v) for v in m.X_thresholds_],"y":[float(v) for v in m.y_thresholds_]}
        return cfg,lambda q:np.interp(np.asarray(q,dtype=float),m.X_thresholds_,m.y_thresholds_)
    raise ValueError(method)


def select_calibration(oof:pd.DataFrame)->tuple[dict[str,Any],pd.DataFrame,dict[str,Any]]:
    methods=["none","platt","isotonic"];scores={}
    # Temporal calibration selection: calibrate on earlier validation years, test later ones.
    for method in methods:
        parts=[]
        for target in [2023,2024]:
            train=oof[oof["year"]<target];test=oof[oof["year"]==target]
            if train.empty or test.empty:continue
            _,fn=_fit_calibrator(method,train["p_full_raw"].to_numpy(),train["actual_hr"].to_numpy())
            q=np.clip(fn(test["p_full_raw"].to_numpy()),1e-6,1-1e-6)
            parts.append((brier(test["actual_hr"],q),ece(test["actual_hr"],q)))
        scores[method]={"mean_brier":float(np.mean([x[0] for x in parts])) if parts else math.inf,"mean_ece":float(np.mean([x[1] for x in parts])) if parts else math.inf}
    # Prefer lowest Brier; ECE breaks near-ties. Avoid isotonic if it only wins microscopically.
    ranked=sorted(methods,key=lambda m:(scores[m]["mean_brier"],scores[m]["mean_ece"],0 if m=="platt" else 1))
    winner=ranked[0]
    if winner=="isotonic" and scores["platt"]["mean_brier"]<=scores["isotonic"]["mean_brier"]+0.00025:
        winner="platt"
    cfg,fn=_fit_calibrator(winner,oof["p_full_raw"].to_numpy(),oof["actual_hr"].to_numpy())
    calibrated=oof.copy();calibrated["p_full"]=np.clip(fn(calibrated["p_full_raw"].to_numpy()),1e-6,1-1e-6)
    return cfg,calibrated,{"selection_scores":scores,"selected":winner,"metrics":metric_bundle(calibrated["actual_hr"],calibrated["p_full"])}


def select_probability_thresholds(oof:pd.DataFrame)->dict[str,float]:
    """Choose stable, mutually-exclusive PRIMARY/SECONDARY/WATCH probability bands.

    PRIMARY is selected first from a stable upper-tail region with positive lift in
    every validation season, meaningful support, and <=3 percentage points maximum
    calibration gap.  SECONDARY and WATCH are then selected as *bands below PRIMARY*,
    not cumulative copies of the same threshold.  A valid tier system must preserve
    actual HR ordering PRIMARY > SECONDARY > WATCH > NO_BET in every validation year,
    with at least 1,000 observations (or 2% of the season, whichever is larger) in
    each actionable band and <=3pp calibration gap for PRIMARY/SECONDARY/WATCH.

    If either the PRIMARY tail or the tier separation lacks stable support, freeze is
    blocked rather than collapsing two labels onto the same probability threshold.
    """
    candidates=np.unique(np.quantile(oof["p_full"],np.linspace(.50,.96,93)))
    rows=[]
    for t in candidates:
        lifts=[];ns=[];cal_errors=[]
        valid=True
        for _,g in oof.groupby("year"):
            selected=g[g["p_full"]>=t]
            min_n=max(500,int(len(g)*.02))
            if len(selected)<min_n:
                valid=False;break
            lifts.append(float(selected["actual_hr"].mean()-g["actual_hr"].mean()))
            ns.append(len(selected))
            cal_errors.append(abs(float(selected["p_full"].mean()-selected["actual_hr"].mean())))
        if valid:
            rows.append({"threshold":float(t),"min_lift":min(lifts),"min_n":min(ns),"max_calibration_gap":max(cal_errors)})

    feasible=[r for r in rows if r["min_lift"]>0.0 and r["max_calibration_gap"]<=0.03]
    if not feasible:
        return {
            "primary_probability":1.0,"secondary_probability":1.0,"watch_probability":1.0,
            "primary_min_lift":0.0,"primary_min_n":0.0,"primary_max_calibration_gap":1.0,
            "tier_min_separation":0.0,"tier_min_n":0.0,"tier_max_calibration_gap":1.0,
            "threshold_support_failed":1.0,
        }

    # Stable-region rule for PRIMARY: stay within 95% of the best worst-season lift,
    # then choose the lowest threshold / largest support rather than the exact peak.
    best=max(r["min_lift"] for r in feasible)
    stable=[r for r in feasible if r["min_lift"]>=.95*best]
    chosen=min(stable,key=lambda r:r["threshold"])
    primary=float(chosen["threshold"])

    # Search data-derived thresholds below PRIMARY.  The ranges intentionally cover
    # broad quantile neighborhoods; the final pair is chosen on multi-season band
    # stability, not on sportsbook ROI or a single-season optimum.
    primary_q=float((oof["p_full"]<primary).mean())
    secondary_q_lo=max(.05,primary_q-.20)
    secondary_q_hi=max(secondary_q_lo+.01,primary_q-.025)
    secondary_q_hi=min(primary_q-.005,secondary_q_hi)
    watch_q_lo=max(.02,min(.30,primary_q-.30))
    watch_q_hi=max(.15,primary_q-.08)
    watch_q_hi=min(primary_q-.01,watch_q_hi)

    secondary_ts=sorted(set(float(oof["p_full"].quantile(q)) for q in np.linspace(secondary_q_lo,secondary_q_hi,30)))
    watch_ts=sorted(set(float(oof["p_full"].quantile(q)) for q in np.linspace(watch_q_lo,watch_q_hi,35)))

    def band_stats(g:pd.DataFrame,lo:float,hi:float|None=None)->dict[str,float]|None:
        x=g[g["p_full"]>=lo] if hi is None else g[(g["p_full"]>=lo)&(g["p_full"]<hi)]
        if x.empty:return None
        pred=float(x["p_full"].mean());actual=float(x["actual_hr"].mean())
        return {"n":float(len(x)),"pred":pred,"actual":actual,"gap":actual-pred}

    band_candidates=[]
    for secondary in secondary_ts:
        for watch in watch_ts:
            if not (watch<secondary<primary):continue
            max_gap=0.0;min_sep=math.inf;min_band_n=math.inf;valid=True
            for _,g in oof.groupby("year"):
                p=band_stats(g,primary)
                s=band_stats(g,secondary,primary)
                w=band_stats(g,watch,secondary)
                n=band_stats(g,-1.0,watch)
                if any(x is None for x in [p,s,w,n]):valid=False;break
                required=max(1000,int(len(g)*.02))
                if min(p["n"],s["n"],w["n"])<required:valid=False;break
                if not (p["actual"]>s["actual"]>w["actual"]>n["actual"]):valid=False;break
                year_gap=max(abs(p["gap"]),abs(s["gap"]),abs(w["gap"]))
                if year_gap>0.03:valid=False;break
                max_gap=max(max_gap,year_gap)
                min_sep=min(min_sep,p["actual"]-s["actual"],s["actual"]-w["actual"],w["actual"]-n["actual"])
                min_band_n=min(min_band_n,p["n"],s["n"],w["n"])
            if valid:
                band_candidates.append({
                    "secondary":float(secondary),"watch":float(watch),
                    "max_gap":float(max_gap),"min_sep":float(min_sep),"min_n":float(min_band_n),
                })

    if not band_candidates:
        return {
            "primary_probability":primary,"secondary_probability":primary,"watch_probability":primary,
            "primary_min_lift":float(chosen["min_lift"]),"primary_min_n":float(chosen["min_n"]),
            "primary_max_calibration_gap":float(chosen["max_calibration_gap"]),
            "tier_min_separation":0.0,"tier_min_n":0.0,"tier_max_calibration_gap":1.0,
            "threshold_support_failed":1.0,
        }

    # Best supported tier system: lowest worst calibration gap first, then widest
    # minimum realized separation, then largest minimum sample size.
    tier=min(band_candidates,key=lambda r:(r["max_gap"],-r["min_sep"],-r["min_n"]))
    secondary=float(tier["secondary"]);watch=float(tier["watch"])
    return {
        "primary_probability":primary,"secondary_probability":secondary,"watch_probability":watch,
        "primary_min_lift":float(chosen["min_lift"]),"primary_min_n":float(chosen["min_n"]),
        "primary_max_calibration_gap":float(chosen["max_calibration_gap"]),
        "tier_min_separation":float(tier["min_sep"]),"tier_min_n":float(tier["min_n"]),
        "tier_max_calibration_gap":float(tier["max_gap"]),
        "threshold_support_failed":0.0,
    }


def derive_gate_support(oof:pd.DataFrame,thresholds:dict[str,float])->dict[str,float]:
    p=thresholds["primary_probability"];s=thresholds["secondary_probability"]
    primary=oof[oof["p_full"]>=p];secondary=oof[oof["p_full"]>=s]
    def q(df,col,qv,default):
        return float(df[col].quantile(qv)) if not df.empty else float(default)
    return {
        "primary_confidence":q(primary,"reliability_proxy",.25,100),
        "secondary_confidence":q(secondary,"reliability_proxy",.15,100),
        # The current production Matchup Score is a presentation/comparative transform,
        # not an independently validated predictive dimension.  Keep its gate disabled
        # in the first frozen candidate rather than double-count probability strength.
        "primary_matchup":0.0,
        "secondary_matchup":0.0,
        "max_primary_ood":q(primary,"ood_proxy",.90,0),
        "max_bet_ood":q(secondary,"ood_proxy",.975,0),
        "confidence_high":q(primary,"reliability_proxy",.50,100),
        "confidence_medium":q(secondary,"reliability_proxy",.20,100),
        "confidence_low":q(oof,"reliability_proxy",.10,0),
    }


def ablation_report(df:pd.DataFrame)->dict[str,Any]:
    full_arts,_=walk_forward(df,CORE_FEATURES)
    report={"FULL":{str(a.validation_year):a.metrics["full"] for a in full_arts}}
    for group,cols in FEATURE_GROUPS.items():
        features=[f for f in CORE_FEATURES if f not in cols]
        arts,_=walk_forward(df,features)
        report[f"NO_{group}"]={str(a.validation_year):a.metrics["full"] for a in arts}
    return report


def fit_final(df:pd.DataFrame,features:list[str])->tuple[StandardScaler,LogisticRegression]:
    return _fit_per_pa(df[df["game_date"].dt.year<=2024],features)


def validation_tolerances(calibrated_oof:pd.DataFrame)->dict[str,float]:
    annual=[]
    for year,g in calibrated_oof.groupby("year"):
        annual.append({"year":int(year),**metric_bundle(g["actual_hr"],g["p_full"])})
    b=np.array([x["brier"] for x in annual],float);e=np.array([x["ece"] for x in annual],float)
    return {
        "validation_annual":annual,
        "max_holdout_brier":float(np.mean(b)+max(2*np.std(b,ddof=1) if len(b)>1 else 0,.005)),
        "max_holdout_ece":float(np.mean(e)+max(2*np.std(e,ddof=1) if len(e)>1 else 0,.01)),
        "min_holdout_monotonicity":float(max(0.60,min(x["monotonicity"] for x in annual)-0.10)),
        "must_beat_baseline_a":True,"must_beat_baseline_b":True,"must_beat_baseline_c":True,
    }
