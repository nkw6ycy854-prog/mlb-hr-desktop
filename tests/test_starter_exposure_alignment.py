import numpy as np
from pathlib import Path

from mlb_hr.domain.models import FeatureVector
from mlb_hr.features.bullpen import BullpenComponent
from mlb_hr.features.engine import CandidateFeatureBundle
from mlb_hr.features.exposure import StarterExposure
from mlb_hr.features.pa import PAProjection
from mlb_hr.features.park import ParkEnvironmentResult
from mlb_hr.model.inference import ProbabilityEngine
from mlb_hr.model.package import ModelPackage
from training.modeling import _exposure_probability


def _bundle(pkg, q_by_pa):
    vals=dict(pkg.manifest.feature_means)
    vals["batter_hr_pa"]=0.03
    vals["pitcher_hr_bf"]=0.06
    rel={k:.8 for k in ["HISTORY","CURRENT_PROFILE","SPLITS","PITCH_TYPE","VELOCITY","ZONE","SIMILAR_PITCHERS","BVP","PA_OPPORTUNITY","STARTER_EXPOSURE","BULLPEN","PARK_ENVIRONMENT"]}
    fv=FeatureVector(10,20,1,vals,rel,[],snapshot_id="exposure-test")
    pa=PAProjection({4:1.0},4.0,1,0,.9)
    exp=StarterExposure(q_by_pa,sum(q_by_pa.values()),4-sum(q_by_pa.values()),.8,18)
    bp=BullpenComponent(.04,.5,.5,.8,10,.2,[])
    park=ParkEnvironmentResult(1,1,0,0,0,.8,.8,[],[])
    return CandidateFeatureBundle(fv,pa,exp,bp,park,1000,1000,.8,.8,.8,.06,.03)


def test_runtime_uses_batter_baseline_after_starter_exit():
    root=Path(__file__).resolve().parents[1]
    pkg=ModelPackage(root/"model_packages"/"development_baseline")
    # Development package may have a nonzero bullpen scale; force the Candidate-2
    # neutral fallback for this contract test without touching the package on disk.
    pkg.manifest.uncertainty["bullpen_adjustment_scale"]=0.0
    eng=ProbabilityEngine(pkg)

    all_sp=eng.predict(_bundle(pkg,{1:1.0,2:1.0,3:1.0,4:1.0}))
    one_sp=eng.predict(_bundle(pkg,{1:1.0,2:0.0,3:0.0,4:0.0}))

    assert abs(one_sp.p_bp_per_pa-0.03)<1e-9
    assert one_sp.raw_game_probability < all_sp.raw_game_probability


def test_training_exposure_probability_reverts_to_neutral_baseline():
    class E:
        q_by_pa={1:1.0,2:0.0,3:0.0,4:0.0}
    p=_exposure_probability(.10,.03,{"4":1.0},E())
    expected=1-(1-.10)*(1-.03)**3
    assert np.isclose(p,expected)
