from mlb_hr.domain.enums import SettlementStatus,PlayerAppearanceStatus
from mlb_hr.postgame.engine import PostgameEngine


def final_feed(hr=True):
    event='home_run' if hr else 'single'
    return {'gameData':{'status':{'abstractGameState':'Final','detailedState':'Final'}},'liveData':{'plays':{'allPlays':[{'about':{'isComplete':True},'matchup':{'batter':{'id':10},'pitcher':{'id':20}},'result':{'eventType':event}}]},'boxscore':{'teams':{'away':{'pitchers':[20,21],'players':{'ID10':{'battingOrder':'100','stats':{'batting':{'homeRuns':1 if hr else 0,'plateAppearances':1}}}}},'home':{'pitchers':[30],'players':{}}}}}}


def test_postgame_reconciles_hr_and_box():
    r=PostgameEngine().evaluate(prediction_id='p',game_pk=1,player_id=10,feed=final_feed(True)).record
    assert r.status==SettlementStatus.PROVISIONAL_SETTLEMENT
    assert r.actual_hr_binary==1 and r.actual_pa==1 and r.actual_pa_vs_starter==1
    assert r.appearance_status==PlayerAppearanceStatus.STARTED_AND_BATTED


def test_postponed_is_not_a_miss():
    feed={'gameData':{'status':{'abstractGameState':'Preview','detailedState':'Postponed'}}}
    r=PostgameEngine().evaluate(prediction_id='p',game_pk=1,player_id=10,feed=feed).record
    assert r.status==SettlementStatus.POSTPONED and r.actual_hr_binary is None
