from __future__ import annotations

from dataclasses import fields
import hashlib
import json
from pathlib import Path
from typing import Any

from mlb_hr.domain.models import ModelPackageManifest


class ModelPackageError(RuntimeError):
    pass


class ModelPackage:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        manifest_path = self.path / "model_manifest.json"
        if not manifest_path.exists():
            raise ModelPackageError(f"Missing model manifest: {manifest_path}")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        allowed = {f.name for f in fields(ModelPackageManifest)}
        unknown = set(raw) - allowed
        if unknown:
            raise ModelPackageError(f"Unknown manifest fields: {sorted(unknown)}")
        self.manifest = ModelPackageManifest(**raw)
        computed = self.compute_hash(raw)
        if self.manifest.package_hash and self.manifest.package_hash != computed:
            raise ModelPackageError("MODEL_PACKAGE checksum mismatch")
        self.package_hash = computed

    @staticmethod
    def compute_hash(raw: dict[str, Any]) -> str:
        clean = dict(raw)
        clean["package_hash"] = ""
        canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    @property
    def release_ready(self) -> bool:
        return bool(self.manifest.release_ready)

    @property
    def feature_config(self) -> dict[str, Any]:
        return dict(self.manifest.metadata.get("feature_config", {}))
