from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from mlb_hr.domain.enums import *
from mlb_hr.domain.models import *
from mlb_hr.storage.sqlite import SQLiteStore


def make_prediction(pid,snapshot,prob=.2):
    return Prediction(pid,snapshot,1,PlayerRef(10,'Batter'),PlayerRef(20,'Pitcher'),'A','B',datetime.now(timezone.utc),prob,prob,80,'A',80,80,ConfidenceLabel.HIGH,ProbabilityDistribution(prob,prob-.02,prob,prob+.02,.04,90),ModelClassification.PRIMARY,UserActionLabel.RECOMMENDED,IntegrityStatus.PASS,CriticVerdict.PASS,['Strong'],None,[],'V1','F1','C1','Q1',ModelHealth.GREEN,datetime.now(timezone.utc))


def make_combo(filter_status=CombinationFilterStatus.QUALIFIED):
    leg=CombinationLeg('pred-1',10,'Batter',.2,ModelClassification.PRIMARY,1)
    return Combination(str(uuid4()),'BEST_2_MAN',[leg],.04,80.0,filter_status,None,None,[])


def test_prediction_revisions_latest_only(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'db.sqlite',root/'migrations');st.migrate()
    for sid in ['s1','s2']:
        st.save_snapshot(snapshot_id=sid,game_pk=1,lineup={},starter={},weather=None,source_timestamps={},feature_vector={},model_package_hash='h',deterministic_seed=1,created_at=datetime.now(timezone.utc))
    p1=make_prediction('p1','s1');st.save_prediction(p1);st.lock_prediction('p1')
    p2=make_prediction('p2','s2',.21);st.save_prediction(p2);st.lock_prediction('p2')
    rows=st.latest_prediction_rows()
    assert len(rows)==1 and rows[0]['prediction_id']=='p2'
    pending=st.pending_predictions()
    assert len(pending)==1 and pending[0]['prediction_id']=='p2'


def test_combination_settlement_tables_migrate(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'combo.db',root/'migrations');st.migrate()
    with st.connection() as con:
        names={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'combination_settlements' in names


def test_confirmed_scratch_invalidates_old_latest(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'inv.db',root/'migrations');st.migrate()
    st.save_snapshot(snapshot_id='s1',game_pk=1,lineup={},starter={},weather=None,source_timestamps={},feature_vector={},model_package_hash='h',deterministic_seed=1,created_at=datetime.now(timezone.utc))
    p=make_prediction('p1','s1');st.save_prediction(p);st.lock_prediction('p1')
    changes=st.invalidate_stale_predictions(1,{999:20})
    assert changes and changes[0]['reason']=='POST_LOCK_LINEUP_INVALIDATION'
    assert st.pending_predictions()==[]


def test_combination_filter_status_persists(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'db.sqlite',root/'migrations');st.migrate()
    combo=make_combo(filter_status=CombinationFilterStatus.FALLBACK)
    st.save_combination(combo)
    with st.connection() as con:
        row=con.execute("SELECT filter_status FROM combinations WHERE combination_id=?",(combo.combination_id,)).fetchone()
    assert row['filter_status']=='FALLBACK'


def test_history_prediction_rows_include_settlement_and_pnl(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'hist.db',root/'migrations');st.migrate()
    st.save_snapshot(snapshot_id='s1',game_pk=1,lineup={},starter={},weather=None,source_timestamps={},feature_vector={},model_package_hash='h',deterministic_seed=1,created_at=datetime.now(timezone.utc))
    p=make_prediction('p1','s1',.3);st.save_prediction(p);st.lock_prediction('p1')
    st.save_model_ledger(prediction_id='p1',reference_stake=10.0,odds_at_prediction=150,decimal_odds=2.5,implied_probability=.4,edge_pp=5.0)
    st.save_settlement(ResultRecord(prediction_id='p1',game_pk=1,player_id=10,status=SettlementStatus.CONFIRMED_SETTLEMENT,actual_hr_count=1,actual_hr_binary=1))
    st.apply_paper_settlement('p1',won=True)

    rows=st.history_prediction_rows()
    assert len(rows)==1
    row=rows[0]
    assert row['prediction_id']=='p1'
    assert row['classification']=='PRIMARY'
    assert float(row['final_probability'])==.3
    assert row['odds_at_prediction']==150
    assert row['settlement_status']=='CONFIRMED_SETTLEMENT'
    assert row['actual_hr_binary']==1
    assert row['pnl_amount'] is not None


def test_history_combination_rows_include_filter_status_and_settlement(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'hist2.db',root/'migrations');st.migrate()
    combo=make_combo(filter_status=CombinationFilterStatus.QUALIFIED)
    st.save_combination(combo)
    st.save_combination_settlement(combo.combination_id,status='CONFIRMED_SETTLEMENT',won=True,void_leg_count=0,profit_loss=25.0)

    rows=st.history_combination_rows()
    assert len(rows)==1
    row=rows[0]
    assert row['combination_id']==combo.combination_id
    assert row['filter_status']=='QUALIFIED'
    assert row['combination_status']=='CONFIRMED_SETTLEMENT'
    assert row['won']==1
    assert row['profit_loss']==25.0


def test_prediction_rows_by_ids_returns_map(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'hist3.db',root/'migrations');st.migrate()
    st.save_snapshot(snapshot_id='s1',game_pk=1,lineup={},starter={},weather=None,source_timestamps={},feature_vector={},model_package_hash='h',deterministic_seed=1,created_at=datetime.now(timezone.utc))
    p=make_prediction('p1','s1',.3);st.save_prediction(p)

    rows=st.prediction_rows_by_ids(['p1','missing'])
    assert set(rows.keys())=={'p1'}
    assert rows['p1']['player_name']=='Batter'


def test_healthcheck_reports_true_on_working_database(tmp_path:Path):
    root=Path(__file__).resolve().parents[1]
    st=SQLiteStore(tmp_path/'health.db',root/'migrations');st.migrate()
    assert st.healthcheck() is True
