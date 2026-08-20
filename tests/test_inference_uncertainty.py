from pathlib import Path
from mlb_hr.domain.models import FeatureVector
from mlb_hr.features.bullpen import BullpenComponent
from mlb_hr.features.engine import CandidateFeatureBundle
from mlb_hr.features.exposure import StarterExposure
from mlb_hr.features.pa import PAProjection
from mlb_hr.features.park import ParkEnvironmentResult
from mlb_hr.model.package import ModelPackage
from mlb_hr.model.inference import ProbabilityEngine
from mlb_hr.uncertainty.engine import UncertaintyEngine


def bundle(pkg):
    vals=dict(pkg.manifest.feature_means);vals['batter_hr_pa']=.05;vals['pitcher_hr_bf']=.04
    rel={k:.8 for k in ['HISTORY','CURRENT_PROFILE','SPLITS','PITCH_TYPE','VELOCITY','ZONE','SIMILAR_PITCHERS','BVP','PA_OPPORTUNITY','STARTER_EXPOSURE','BULLPEN','PARK_ENVIRONMENT']}
    fv=FeatureVector(10,20,1,vals,rel,[],snapshot_id='fixed-snapshot')
    pa=PAProjection({4:.5,5:.5},4.5,1,.5,.85)
    exp=StarterExposure({1:.99,2:.95,3:.7,4:.2,5:.05},2.8,1.7,.8,18)
    bp=BullpenComponent(.032,.7,.3,.75,20,.4,[])
    park=ParkEnvironmentResult(1,1,0,0,0,.8,.8,[],[])
    return CandidateFeatureBundle(fv,pa,exp,bp,park,1000,1200,.8,.8,.8,.04,.03)


def test_inference_and_uncertainty_are_deterministic():
    root=Path(__file__).resolve().parents[1];pkg=ModelPackage(root/'model_packages'/'development_baseline')
    eng=ProbabilityEngine(pkg);b=bundle(pkg);p=eng.predict(b)
    u=UncertaintyEngine(eng);a=u.evaluate(b,p.final_probability);c=u.evaluate(b,p.final_probability)
    assert 0<p.final_probability<1
    assert a.distribution.p10<=a.distribution.p50<=a.distribution.p90
    assert a.distribution==c.distribution and a.confidence_score==c.confidence_score
