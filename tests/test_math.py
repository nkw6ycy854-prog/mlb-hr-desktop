from mlb_hr.domain.math import american_to_decimal,decimal_to_implied,game_hr_probability,payout_for_stake


def test_american_odds_and_payout():
    assert american_to_decimal(300)==4.0
    assert round(decimal_to_implied(4.0),4)==0.25
    total,profit=payout_for_stake(10,300)
    assert total==40 and profit==30
    assert round(american_to_decimal(-200),3)==1.5


def test_game_probability_integrates_pa_distribution():
    p=game_hr_probability(.05,{4:.5,5:.5})
    assert .19 < p < .22
