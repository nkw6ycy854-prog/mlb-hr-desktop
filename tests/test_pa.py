from mlb_hr.features.pa import PAOpportunityEngine


def test_pa_engine_accepts_trained_slot_distribution():
    e=PAOpportunityEngine({'pa_distribution_by_slot':{'1':{'4':.25,'5':.75}}})
    p=e.project(1,home_team=False,survival_probability=1.0)
    assert abs(p.expected_pa-4.75)<1e-9
