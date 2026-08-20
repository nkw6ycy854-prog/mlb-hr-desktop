from datetime import datetime,timezone
from pathlib import Path
from mlb_hr.domain.enums import *
from mlb_hr.domain.models import *
from mlb_hr.storage.sqlite import SQLiteStore


def make_prediction(pid,snapshot,prob=.2):
    return Prediction(pid,snapshot,1,PlayerRef(10,'Batter'),PlayerRef(20,'Pitcher'),'A','B',datetime.now(timezone.utc),prob,prob,80,'A',80,80,ConfidenceLabel.HIGH,ProbabilityDistribution(prob,prob-.02,prob,prob+.02,.04,90),ModelClassification.PRIMARY,UserActionLabel.RECOMMENDED,IntegrityStatus.PASS,CriticVerdict.PASS,['Strong'],None,[],'V1','F1','C1','Q1',ModelHealth.GREEN,datetime.now(timezone.utc))


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
    with st.connect() as con:
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
