import numpy as np
import pandas as pd
from training.modeling import select_probability_thresholds


def _ordered_frame():
    rows=[]
    # Large deterministic sample with monotone realized HR rates by probability band.
    for year,shift in [(2022,-.015),(2023,.005),(2024,-.005)]:
        rng=np.random.default_rng(year)
        for i in range(12000):
            p=.055+.15*(i/11999)
            true=np.clip(p+shift,0.001,.95)
            y=int(rng.random()<true)
            rows.append({"year":year,"p_full":p,"actual_hr":y,"reliability_proxy":75.,"ood_proxy":10.})
    return pd.DataFrame(rows)


def test_thresholds_are_strictly_separated_when_supported():
    t=select_probability_thresholds(_ordered_frame())
    assert t["threshold_support_failed"]==0
    assert t["primary_probability"]>t["secondary_probability"]>t["watch_probability"]
    assert t["tier_min_n"]>=1000
    assert t["tier_max_calibration_gap"]<=.03
    assert t["tier_min_separation"]>0
