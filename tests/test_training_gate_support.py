import pandas as pd
from training.modeling import derive_gate_support


def test_first_candidate_does_not_double_count_unvalidated_matchup_score():
    oof=pd.DataFrame({
        "p_full":[.10,.15,.20,.25],
        "reliability_proxy":[40.,55.,70.,85.],
        "matchup_score_proxy":[50.,60.,80.,95.],
        "ood_proxy":[20.,30.,40.,50.],
    })
    support=derive_gate_support(oof,{"primary_probability":.20,"secondary_probability":.15})
    assert support["primary_matchup"]==0.0
    assert support["secondary_matchup"]==0.0
