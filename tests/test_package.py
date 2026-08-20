from pathlib import Path
from mlb_hr.model.package import ModelPackage


def test_development_package_is_valid_but_not_release_ready():
    root=Path(__file__).resolve().parents[1]
    p=ModelPackage(root/'model_packages'/'development_baseline')
    assert p.package_hash
    assert p.release_ready is False
    assert p.manifest.holdout_period=='2025_LOCKED_NOT_RUN'
