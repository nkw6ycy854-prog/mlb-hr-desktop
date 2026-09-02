"""Regression gate for the Windows FULL release package.

These tests inspect real, generated ZIP files (built via the same assembler
used by scripts/create_windows_full_release.sh and the hardened CI gate) --
not just string-matching the packaging script's source text. They exist
because MLB-HR-Windows-v1.0.0.zip shipped with zero runtime_data/statcast
files: the CI gate never enforced it, and the only prior test only checked
that the assembler script *contained certain substrings*.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts import windows_full_package as wfp


def _make_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "app.exe").write_bytes(b"fake-exe")
    (bundle / "MLB HR.bat").write_text("@echo off\n", encoding="utf-8")
    (bundle / "SELF TEST.bat").write_text("@echo off\n", encoding="utf-8")
    return bundle


def _make_statcast_src(tmp_path: Path, count: int = 2) -> Path:
    src = tmp_path / "statcast_src"
    dates = ["2024-06-01", "2024-06-02", "2024-06-03"][:count]
    for d in dates:
        p = src / "season=2024" / "month=06" / f"statcast_{d}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"placeholder-parquet")
    return src


def _passing_self_test(_bundle_dir: Path) -> dict:
    return {
        "passed": True,
        "checks": {"statcast_runtime_available": True},
        "details": {"runtime_statcast": {"available": True, "parquet_count": 2}},
    }


def _failing_self_test(_bundle_dir: Path) -> dict:
    return {
        "passed": False,
        "checks": {"statcast_runtime_available": False},
        "details": {"runtime_statcast": {"available": False, "parquet_count": 0}},
    }


def test_build_full_package_produces_zip_with_statcast_and_manifest(tmp_path):
    bundle = _make_bundle(tmp_path)
    statcast_src = _make_statcast_src(tmp_path, count=2)
    output_zip = tmp_path / "out" / "MLB-HR-Windows-FULL.zip"
    manifest_path = tmp_path / "out" / "manifest.json"

    manifest = wfp.build_full_package(
        bundle_dir=bundle,
        statcast_src=statcast_src,
        output_zip=output_zip,
        manifest_path=manifest_path,
        app_version="1.0.1",
        model_version="V1.0.0",
        model_hash="4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab",
        release_commit="deadbeef",
        run_self_test=_passing_self_test,
    )

    assert manifest["statcast_parquet_count"] == 2
    assert manifest["statcast_runtime_available"] is True
    assert manifest["self_test_pass"] is True
    assert manifest["app_version"] == "1.0.1"
    assert manifest["model_version"] == "V1.0.0"

    assert output_zip.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["statcast_parquet_count"] == 2

    with zipfile.ZipFile(output_zip) as zf:
        names = zf.namelist()
        parquet_names = [
            n for n in names if n.startswith("runtime_data/statcast/") and n.endswith(".parquet")
        ]
        assert len(parquet_names) == 2
        assert wfp.MANIFEST_NAME in names


def test_build_full_package_raises_when_statcast_source_is_empty(tmp_path):
    bundle = _make_bundle(tmp_path)
    empty_src = tmp_path / "empty_statcast"
    empty_src.mkdir()
    output_zip = tmp_path / "out.zip"

    with pytest.raises(wfp.FullPackageError, match="no Statcast"):
        wfp.build_full_package(
            bundle_dir=bundle,
            statcast_src=empty_src,
            output_zip=output_zip,
            manifest_path=tmp_path / "manifest.json",
            app_version="1.0.1",
            model_version="V1.0.0",
            model_hash="hash",
            release_commit="sha",
            run_self_test=_passing_self_test,
        )
    assert not output_zip.exists()


def test_build_full_package_raises_when_base_bundle_is_incomplete(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "app.exe").write_bytes(b"fake-exe")
    # Missing "MLB HR.bat" / "SELF TEST.bat" -> not a real base artifact.
    statcast_src = _make_statcast_src(tmp_path)

    with pytest.raises(wfp.FullPackageError, match="missing required base artifact"):
        wfp.build_full_package(
            bundle_dir=bundle,
            statcast_src=statcast_src,
            output_zip=tmp_path / "out.zip",
            manifest_path=tmp_path / "manifest.json",
            app_version="1.0.1",
            model_version="V1.0.0",
            model_hash="hash",
            release_commit="sha",
            run_self_test=_passing_self_test,
        )


def test_build_full_package_raises_when_self_test_does_not_confirm_statcast(tmp_path):
    bundle = _make_bundle(tmp_path)
    statcast_src = _make_statcast_src(tmp_path)
    output_zip = tmp_path / "out.zip"

    with pytest.raises(wfp.FullPackageError, match="statcast_runtime_available"):
        wfp.build_full_package(
            bundle_dir=bundle,
            statcast_src=statcast_src,
            output_zip=output_zip,
            manifest_path=tmp_path / "manifest.json",
            app_version="1.0.1",
            model_version="V1.0.0",
            model_hash="hash",
            release_commit="sha",
            run_self_test=_failing_self_test,
        )
    assert not output_zip.exists()


def test_build_full_package_uses_real_selftest_module_end_to_end(tmp_path, monkeypatch):
    """Integration test with no mocks: runs the actual mlb_hr.selftest module against
    an assembled runtime_data dir, the same way the production packaging path does.
    """
    import mlb_hr.selftest as selftest

    bundle = _make_bundle(tmp_path)
    statcast_src = _make_statcast_src(tmp_path, count=2)

    def run_real_self_test(assembled_bundle_dir: Path) -> dict:
        monkeypatch.setenv("MLB_HR_DATA_DIR", str(assembled_bundle_dir / "runtime_data"))
        try:
            return selftest.run_self_test(require_runtime_data=True)
        finally:
            monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)

    manifest = wfp.build_full_package(
        bundle_dir=bundle,
        statcast_src=statcast_src,
        output_zip=tmp_path / "out.zip",
        manifest_path=tmp_path / "manifest.json",
        app_version="1.0.1",
        model_version="V1.0.0",
        model_hash="hash",
        release_commit="sha",
        run_self_test=run_real_self_test,
    )

    assert manifest["statcast_runtime_available"] is True
    assert manifest["self_test_pass"] is True


def test_validate_full_release_zip_accepts_valid_full_package(tmp_path):
    bundle = _make_bundle(tmp_path)
    statcast_src = _make_statcast_src(tmp_path, count=3)
    output_zip = tmp_path / "out.zip"
    wfp.build_full_package(
        bundle_dir=bundle,
        statcast_src=statcast_src,
        output_zip=output_zip,
        manifest_path=tmp_path / "manifest.json",
        app_version="1.0.1",
        model_version="V1.0.0",
        model_hash="hash",
        release_commit="sha",
        run_self_test=_passing_self_test,
    )

    manifest = wfp.validate_full_release_zip(output_zip)
    assert manifest["statcast_parquet_count"] == 3


def test_validate_full_release_zip_rejects_raw_ci_artifact_without_runtime_data(tmp_path):
    """Reproduces the exact shipped v1.0.0 bug: app.exe + launchers, no runtime_data."""
    raw_zip = tmp_path / "MLB-HR-Windows-App.zip"
    with zipfile.ZipFile(raw_zip, "w") as zf:
        zf.writestr("app.exe", "fake-exe")
        zf.writestr("MLB HR.bat", "@echo off")
        zf.writestr("SELF TEST.bat", "@echo off")

    with pytest.raises(wfp.FullPackageError, match="runtime_data/statcast"):
        wfp.validate_full_release_zip(raw_zip)


def test_validate_full_release_zip_rejects_empty_statcast_directory(tmp_path):
    zip_path = tmp_path / "hollow.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("app.exe", "fake-exe")
        zf.writestr("runtime_data/statcast/season=2024/month=06/.keep", "")
        zf.writestr(
            wfp.MANIFEST_NAME,
            json.dumps(
                {
                    "statcast_parquet_count": 0,
                    "statcast_runtime_available": False,
                    "self_test_pass": False,
                }
            ),
        )

    with pytest.raises(wfp.FullPackageError, match="0 parquet"):
        wfp.validate_full_release_zip(zip_path)


def test_validate_full_release_zip_rejects_zip_without_manifest_marker(tmp_path):
    """A zip hand-stuffed with parquet files, bypassing the real FULL assembler."""
    zip_path = tmp_path / "manual.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("app.exe", "fake-exe")
        zf.writestr(
            "runtime_data/statcast/season=2024/month=06/statcast_2024-06-01.parquet", "data"
        )

    with pytest.raises(wfp.FullPackageError, match=wfp.MANIFEST_NAME):
        wfp.validate_full_release_zip(zip_path)


def test_cli_build_and_validate_round_trip_via_subprocess(tmp_path):
    """Exercises the exact CLI invocation used by create_windows_full_release.sh and
    the CI workflow: argv, JSON --self-test-cmd, subprocess self-test, and stdout.
    """
    import json as _json
    import subprocess
    import sys

    bundle = _make_bundle(tmp_path)
    statcast_src = _make_statcast_src(tmp_path, count=2)
    output_zip = tmp_path / "out.zip"
    manifest_path = tmp_path / "manifest.json"

    # No MLB_HR_DATA_DIR reliance -- the fake self-test instead checks its own
    # cwd (which _subprocess_self_test sets to bundle_dir, matching how a
    # real user launches the app from inside the extracted folder) for the
    # assembled runtime_data/statcast directory, same shape as the real
    # discovery this is meant to exercise.
    self_test_script = tmp_path / "fake_self_test.py"
    self_test_script.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "found = any(Path.cwd().glob('runtime_data/statcast/season=*/month=*/statcast_*.parquet'))\n"
        "print(json.dumps({'passed': True, 'checks': {'statcast_runtime_available': found}}))\n",
        encoding="utf-8",
    )

    module_path = Path(__file__).resolve().parents[1] / "scripts" / "windows_full_package.py"
    build_cmd = [
        sys.executable,
        str(module_path),
        "build",
        "--bundle-dir", str(bundle),
        "--statcast-src", str(statcast_src),
        "--output-zip", str(output_zip),
        "--manifest-path", str(manifest_path),
        "--app-version", "1.0.1",
        "--model-version", "V1.0.0",
        "--model-hash", "hash",
        "--release-commit", "sha",
        "--self-test-cmd", _json.dumps([sys.executable, str(self_test_script)]),
    ]
    cp = subprocess.run(build_cmd, capture_output=True, text=True, timeout=30, check=False)
    assert cp.returncode == 0, cp.stderr
    assert output_zip.exists()

    validate_cmd = [sys.executable, str(module_path), "validate", "--zip", str(output_zip)]
    cp = subprocess.run(validate_cmd, capture_output=True, text=True, timeout=30, check=False)
    assert cp.returncode == 0, cp.stderr
    manifest = json.loads(cp.stdout)
    assert manifest["statcast_parquet_count"] == 2
    assert manifest["statcast_runtime_available"] is True


def test_validate_full_release_zip_rejects_manifest_reporting_self_test_failure(tmp_path):
    zip_path = tmp_path / "unverified.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("app.exe", "fake-exe")
        zf.writestr(
            "runtime_data/statcast/season=2024/month=06/statcast_2024-06-01.parquet", "data"
        )
        zf.writestr(
            wfp.MANIFEST_NAME,
            json.dumps(
                {
                    "statcast_parquet_count": 1,
                    "statcast_runtime_available": True,
                    "self_test_pass": False,
                }
            ),
        )

    with pytest.raises(wfp.FullPackageError, match="self_test_pass"):
        wfp.validate_full_release_zip(zip_path)


def test_subprocess_self_test_never_injects_mlb_hr_data_dir(tmp_path, monkeypatch):
    """Direct regression guard for the real shipped bug: _subprocess_self_test
    used to unconditionally set MLB_HR_DATA_DIR before running the self-test
    command, which made every self-test (including the CI gate's real
    app.exe) "find" the bundled data via an override a real end user never
    sets -- masking that resolve_app_paths() never looked at
    <bundle_dir>/runtime_data/statcast on its own.
    """
    monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)
    bundle = _make_bundle(tmp_path)
    probe_script = tmp_path / "probe.py"
    probe_script.write_text(
        "import json, os\n"
        "print(json.dumps({'passed': True, 'checks': {'mlb_hr_data_dir_was_set': "
        "'MLB_HR_DATA_DIR' in os.environ}}))\n",
        encoding="utf-8",
    )
    import sys as _sys
    runner = wfp._subprocess_self_test([_sys.executable, str(probe_script)])

    result = runner(bundle)

    assert result["checks"]["mlb_hr_data_dir_was_set"] is False
    assert "MLB_HR_DATA_DIR" not in __import__("os").environ


def test_subprocess_self_test_runs_with_cwd_set_to_bundle_dir(tmp_path):
    # Matches how a real user launches the app: from inside the extracted
    # folder, not from wherever the packaging script itself happens to run.
    bundle = _make_bundle(tmp_path)
    probe_script = tmp_path / "cwd_probe.py"
    probe_script.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "print(json.dumps({'passed': True, 'checks': {}, 'cwd': str(Path.cwd())}))\n",
        encoding="utf-8",
    )
    import sys as _sys
    runner = wfp._subprocess_self_test([_sys.executable, str(probe_script)])

    result = runner(bundle)

    assert Path(result["cwd"]).resolve() == bundle.resolve()
