"""Assemble and validate the Windows FULL release package (app.exe + real Statcast).

This module is the single source of truth for turning the bare CI artifact
(app.exe + launchers, no data) into a release-ready package that bundles
runtime_data/statcast and can prove -- via a manifest embedded in the zip --
that a self-test with --require-runtime-data actually confirmed
statcast_runtime_available=true before the zip was produced.

Used by:
  - scripts/create_windows_full_release.sh (real production build, real Statcast)
  - .github/workflows/windows-native.yml (CI gate, fixture Statcast)
  - tests/test_windows_full_package.py (regression gate)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

STATCAST_GLOB = "season=*/month=*/statcast_*.parquet"
MANIFEST_NAME = "RELEASE-MANIFEST.json"
REQUIRED_BASE_FILES = ("app.exe", "MLB HR.bat", "SELF TEST.bat")

SelfTestRunner = Callable[[Path], dict]


class FullPackageError(RuntimeError):
    """Raised when the Windows FULL package cannot be assembled or fails validation."""


def _count_statcast(root: Path) -> int:
    return len(list(root.glob(STATCAST_GLOB)))


def build_full_package(
    *,
    bundle_dir: Path,
    statcast_src: Path,
    output_zip: Path,
    manifest_path: Path,
    app_version: str,
    model_version: str,
    model_hash: str,
    release_commit: str,
    run_self_test: SelfTestRunner,
) -> dict:
    """Assemble a Windows FULL release zip from a base bundle + a Statcast source tree.

    Raises FullPackageError (without producing a zip) if the base bundle isn't a
    real packaged artifact, if there is no Statcast to bundle, if the copy is
    incomplete, or if run_self_test does not confirm
    checks.statcast_runtime_available=true against the assembled package.
    """
    missing = [name for name in REQUIRED_BASE_FILES if not (bundle_dir / name).exists()]
    if missing:
        raise FullPackageError(
            f"bundle_dir {bundle_dir} is missing required base artifact files: {missing}"
        )

    source_count = _count_statcast(statcast_src)
    if source_count == 0:
        raise FullPackageError(f"no Statcast parquet files found under {statcast_src}")

    dest_root = bundle_dir / "runtime_data" / "statcast"
    for parquet_file in statcast_src.glob(STATCAST_GLOB):
        rel = parquet_file.relative_to(statcast_src)
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(parquet_file, dest)

    dest_count = _count_statcast(dest_root)
    if dest_count != source_count:
        raise FullPackageError(
            f"incomplete Statcast copy: {dest_count}/{source_count} files landed in {dest_root}"
        )

    self_test_result = run_self_test(bundle_dir) or {}
    self_test_checks = self_test_result.get("checks", {})
    self_test_pass = bool(self_test_result.get("passed")) and bool(
        self_test_checks.get("statcast_runtime_available")
    )
    if not self_test_pass:
        raise FullPackageError(
            "self-test did not confirm statcast_runtime_available=true for the FULL "
            f"package (self_test_result={json.dumps(self_test_result)})"
        )

    manifest = {
        "app_version": app_version,
        "model_version": model_version,
        "model_hash": model_hash,
        "statcast_parquet_count": dest_count,
        "statcast_runtime_available": True,
        "self_test_pass": True,
        "release_commit": release_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    manifest_json = json.dumps(manifest, indent=2, sort_keys=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest_json, encoding="utf-8")
    (bundle_dir / MANIFEST_NAME).write_text(manifest_json, encoding="utf-8")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(bundle_dir).as_posix())

    return manifest


def validate_full_release_zip(zip_path: Path) -> dict:
    """Inspect a real zip file and raise FullPackageError unless it is a genuine,
    self-test-verified Windows FULL release package.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

        has_statcast_dir = any(n.startswith("runtime_data/statcast/") for n in names)
        if not has_statcast_dir:
            raise FullPackageError(f"{zip_path} does not contain runtime_data/statcast/")

        parquet_entries = [
            n for n in names if n.startswith("runtime_data/statcast/") and n.endswith(".parquet")
        ]
        if not parquet_entries:
            raise FullPackageError(
                f"{zip_path} contains runtime_data/statcast/ but 0 parquet files"
            )

        if MANIFEST_NAME not in names:
            raise FullPackageError(
                f"{zip_path} is missing {MANIFEST_NAME} -- not produced by the FULL "
                "release assembler (scripts/windows_full_package.py)"
            )
        manifest = json.loads(zf.read(MANIFEST_NAME))

        manifest_count = manifest.get("statcast_parquet_count", 0)
        if manifest_count != len(parquet_entries):
            raise FullPackageError(
                f"manifest statcast_parquet_count ({manifest_count}) does not match "
                f"actual parquet entries in zip ({len(parquet_entries)})"
            )
        if not manifest.get("statcast_runtime_available"):
            raise FullPackageError(f"{zip_path} manifest reports statcast_runtime_available=false")
        if not manifest.get("self_test_pass"):
            raise FullPackageError(f"{zip_path} manifest reports self_test_pass=false")

    return manifest


def _subprocess_self_test(args: list[str]) -> SelfTestRunner:
    def _run(bundle_dir: Path) -> dict:
        import os

        prior = os.environ.get("MLB_HR_DATA_DIR")
        os.environ["MLB_HR_DATA_DIR"] = str(bundle_dir / "runtime_data")
        try:
            cp = subprocess.run(args, capture_output=True, text=True, timeout=90, check=False)
        finally:
            if prior is None:
                os.environ.pop("MLB_HR_DATA_DIR", None)
            else:
                os.environ["MLB_HR_DATA_DIR"] = prior
        try:
            return json.loads(cp.stdout.strip())
        except json.JSONDecodeError as exc:
            raise FullPackageError(
                f"self-test command {args} did not print JSON: {cp.stdout[-2000:]}"
            ) from exc

    return _run


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="assemble a Windows FULL release zip")
    build.add_argument("--bundle-dir", type=Path, required=True)
    build.add_argument("--statcast-src", type=Path, required=True)
    build.add_argument("--output-zip", type=Path, required=True)
    build.add_argument("--manifest-path", type=Path, required=True)
    build.add_argument("--app-version", required=True)
    build.add_argument("--model-version", required=True)
    build.add_argument("--model-hash", required=True)
    build.add_argument("--release-commit", required=True)
    build.add_argument(
        "--self-test-cmd",
        required=True,
        help=(
            "JSON array of argv tokens that run the packaged self-test with "
            "--require-runtime-data and print its JSON report to stdout, e.g. "
            '\'["app.exe", "--self-test", "--require-runtime-data"]\' or '
            '\'["python3", "-m", "mlb_hr.selftest", "--require-runtime-data"]\'. '
            "A JSON array (not a shell string) is required so Windows paths with "
            "backslashes and spaces survive intact."
        ),
    )

    validate = sub.add_parser("validate", help="validate an existing FULL release zip")
    validate.add_argument("--zip", type=Path, required=True, dest="zip_path")

    args = parser.parse_args(argv)

    if args.command == "build":
        try:
            self_test_argv = json.loads(args.self_test_cmd)
        except json.JSONDecodeError as exc:
            raise FullPackageError(
                f"--self-test-cmd must be a JSON array of argv tokens, got: {args.self_test_cmd!r}"
            ) from exc
        manifest = build_full_package(
            bundle_dir=args.bundle_dir,
            statcast_src=args.statcast_src,
            output_zip=args.output_zip,
            manifest_path=args.manifest_path,
            app_version=args.app_version,
            model_version=args.model_version,
            model_hash=args.model_hash,
            release_commit=args.release_commit,
            run_self_test=_subprocess_self_test(self_test_argv),
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    manifest = validate_full_release_zip(args.zip_path)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except FullPackageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
