import numpy as np
import pandas as pd
from training.modeling import select_probability_thresholds


def _frame(overconfident=False):
    rows=[]
    rng=np.random.default_rng(11)
    for year in [2022,2023,2024]:
        for i in range(12000):
            p=.06+.20*(i/11999)
            true_p=p if not overconfident else np.clip(p-.06,0.001,0.99)
            y=int(rng.random()<true_p)
            rows.append({"year":year,"p_full":p,"actual_hr":y,"reliability_proxy":80,"ood_proxy":10})
    return pd.DataFrame(rows)


def test_threshold_policy_requires_tail_calibration_support():
    good=select_probability_thresholds(_frame(False))
    assert good["threshold_support_failed"]==0
    assert good["primary_max_calibration_gap"]<=.03

    bad=select_probability_thresholds(_frame(True))
    assert bad["threshold_support_failed"]==1
