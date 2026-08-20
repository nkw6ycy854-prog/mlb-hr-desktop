from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


def brier(y: Iterable[float], p: Iterable[float]) -> float:
    ya=np.asarray(list(y),dtype=float);pa=np.clip(np.asarray(list(p),dtype=float),1e-9,1-1e-9)
    return float(np.mean((pa-ya)**2)) if len(ya) else math.nan


def log_loss(y: Iterable[float], p: Iterable[float]) -> float:
    ya=np.asarray(list(y),dtype=float);pa=np.clip(np.asarray(list(p),dtype=float),1e-9,1-1e-9)
    return float(-np.mean(ya*np.log(pa)+(1-ya)*np.log(1-pa))) if len(ya) else math.nan


def calibration_table(y: Iterable[float], p: Iterable[float], bins: int=10) -> pd.DataFrame:
    df=pd.DataFrame({"y":list(y),"p":list(p)}).dropna()
    if df.empty:return pd.DataFrame(columns=["bin","n","mean_pred","actual_rate","abs_error"])
    edges=np.linspace(0,1,bins+1)
    # Fixed probability bins retain interpretable calibration; empty bins are omitted.
    df["bin"]=pd.cut(df["p"],edges,include_lowest=True,duplicates="drop")
    out=df.groupby("bin",observed=True).agg(n=("y","size"),mean_pred=("p","mean"),actual_rate=("y","mean")).reset_index()
    out["abs_error"]=(out["mean_pred"]-out["actual_rate"]).abs()
    return out


def ece(y: Iterable[float], p: Iterable[float], bins:int=10)->float:
    tab=calibration_table(y,p,bins)
    if tab.empty:return math.nan
    return float((tab["n"]*tab["abs_error"]).sum()/tab["n"].sum())


def monotonicity_score(y: Iterable[float], p: Iterable[float], bins:int=8)->float:
    df=pd.DataFrame({"y":list(y),"p":list(p)}).dropna()
    if len(df)<50:return 0.0
    try:df["bucket"]=pd.qcut(df["p"],q=min(bins,max(2,len(df)//50)),duplicates="drop")
    except ValueError:return 0.0
    rates=df.groupby("bucket",observed=True)["y"].mean().to_numpy()
    if len(rates)<2:return 0.0
    return float(np.mean(np.diff(rates)>=-0.005))


def metric_bundle(y: Iterable[float], p: Iterable[float])->dict[str,float]:
    yl=list(y);pl=list(p)
    return {"n":len(yl),"brier":brier(yl,pl),"log_loss":log_loss(yl,pl),"ece":ece(yl,pl),"monotonicity":monotonicity_score(yl,pl)}
