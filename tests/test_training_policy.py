import pandas as pd
from training.modeling import select_probability_thresholds


def test_threshold_policy_uses_predictions_not_roi():
    # Deterministic, well-calibrated synthetic seasons: no sportsbook/ROI columns are
    # present, and the policy must still find a supported probability region.
    rows=[]
    for year in [2022,2023,2024]:
        for bucket,p in enumerate([.08,.10,.12,.14,.16,.18,.20,.22,.24,.26]):
            # 1000 observations per bucket with exactly round(p*1000) positives.
            positives=round(p*1000)
            for i in range(1000):
                rows.append({
                    'year':year,
                    'p_full':p,
                    'actual_hr':1 if i<positives else 0,
                    'reliability_proxy':80,
                    'matchup_score_proxy':80,
                    'ood_proxy':10,
                })
    out=select_probability_thresholds(pd.DataFrame(rows))
    assert 0<out['watch_probability']<=out['secondary_probability']<=out['primary_probability']<=1
    assert out['threshold_support_failed']==0
    assert out['primary_max_calibration_gap']<=.03
