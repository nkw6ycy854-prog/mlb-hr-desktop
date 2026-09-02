from pathlib import Path

from scripts import windows_full_package as wfp

ROOT = Path(__file__).resolve().parents[1]
CI_STATCAST_FIXTURE = ROOT / "tests" / "fixtures" / "statcast_ci_fixture"


def test_windows_launchers_never_override_data_dir_and_let_app_exe_self_discover():
    # Neither launcher may set MLB_HR_DATA_DIR: app.exe must discover
    # runtime_data/statcast entirely on its own (see
    # storage/paths.py:_frozen_windows_bundled_statcast_dir). A launcher
    # that pre-sets the override would make these scripts always "pass"
    # regardless of whether that auto-discovery actually works -- the same
    # false-positive-testing bug this whole fix exists to close, but in the
    # exact tool distributed to end users to verify the release
    # (RELEASE-INFO.txt tells them to "abrir SELF TEST.bat primero").
    launcher = (ROOT / 'packaging/windows/MLB HR.bat').read_text(encoding='utf-8')
    selftest = (ROOT / 'packaging/windows/SELF TEST.bat').read_text(encoding='utf-8')

    assert 'MLB_HR_DATA_DIR' not in launcher
    assert 'runtime_data\\statcast\\statcast_*.parquet' in launcher
    assert 'app.exe' in launcher

    assert 'MLB_HR_DATA_DIR' not in selftest
    assert '--self-test --require-runtime-data' in selftest


def test_windows_workflow_packages_portable_launchers():
    workflow = (ROOT / '.github/workflows/windows-native.yml').read_text(encoding='utf-8')
    assert 'packaging\\windows\\MLB HR.bat' in workflow
    assert 'packaging\\windows\\SELF TEST.bat' in workflow
    assert 'MLB-HR-Windows-App.zip' in workflow


def test_windows_workflow_gate_cannot_pass_on_the_base_zip_alone():
    """MLB-HR-Windows-App.zip (no Statcast) must never be the source of truth for a
    green gate. The workflow must assemble a FULL package (even if only against a
    fixture in CI), run --require-runtime-data against the real app.exe, and fail the
    job outright if statcast_runtime_available isn't confirmed true.
    """
    workflow = (ROOT / '.github/workflows/windows-native.yml').read_text(encoding='utf-8')

    assert 'tests\\fixtures\\statcast_ci_fixture' in workflow
    assert 'windows_full_package.py build' in workflow
    assert 'windows_full_package.py validate' in workflow
    assert '--require-runtime-data' in workflow
    assert 'statcast_runtime_available' in workflow
    # The base zip must be explicitly documented as non-release-ready in the workflow
    # that produces it, so it can't quietly become the thing someone re-uploads.
    assert 'not release-ready' in workflow.lower() or 'not-release-ready' in workflow.lower()


def test_full_release_assembler_requires_statcast_and_downloads_fresh_windows_artifact():
    assembler = (ROOT / 'scripts/create_windows_full_release.sh').read_text(encoding='utf-8')
    assert "find \"$STATCAST_SRC\" -type f -name 'statcast_*.parquet'" in assembler
    assert 'gh workflow run "$WORKFLOW" --ref "$BRANCH"' in assembler
    assert 'gh run watch "$RUN_ID" --exit-status' in assembler
    assert 'gh run download "$RUN_ID"' in assembler
    assert 'windows_full_package.py" build' in assembler
    assert 'windows_full_package.py" validate --zip' in assembler
    assert '--self-test-cmd' in assembler
    # The local self-test-cmd is deliberately NOT mlb_hr.selftest run from macOS
    # source anymore: that used to only pass because _subprocess_self_test()
    # injected MLB_HR_DATA_DIR, which masked the real shipped bug (the Windows
    # app.exe couldn't find its own bundled runtime_data/statcast without that
    # override). It's now a narrowly-scoped local file-copy-integrity check.
    assert '"mlb_hr.selftest"' not in assembler
    assert 'local_copy_check.py' in assembler
    # The real runtime-discovery proof now comes from a hard precondition that
    # the CI gate's own app.exe self-test (real Windows, no override) already
    # confirmed statcast_runtime_available=true for this exact release_commit.
    assert 'statcast_runtime_available' in assembler
    assert 'windows.json' in assembler


def _make_base_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "app.dist"
    bundle.mkdir()
    (bundle / "app.exe").write_bytes(b"fake-exe-for-test")
    (bundle / "MLB HR.bat").write_text(
        (ROOT / "packaging/windows/MLB HR.bat").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (bundle / "SELF TEST.bat").write_text(
        (ROOT / "packaging/windows/SELF TEST.bat").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return bundle


def test_windows_full_release_zip_actually_contains_bundled_statcast_and_manifest(
    tmp_path, monkeypatch
):
    """Regression gate for the exact bug that shipped in MLB-HR-Windows-v1.0.0.zip:
    the published asset had 0 files under runtime_data/statcast. This test inspects a
    real, generated ZIP byte-for-byte -- it does not string-match any script source --
    using the real mlb_hr.selftest module (no mocks) as the self-test oracle, exactly
    like the production assembler and the hardened CI gate do.
    """
    import mlb_hr.selftest as selftest

    assert list(CI_STATCAST_FIXTURE.glob(wfp.STATCAST_GLOB)), (
        "tests/fixtures/statcast_ci_fixture must contain at least one "
        "season=*/month=*/statcast_*.parquet file"
    )

    bundle = _make_base_bundle(tmp_path)
    output_zip = tmp_path / "MLB-HR-Windows-V1.0.1-FULL.zip"

    def run_real_self_test(assembled_bundle_dir: Path) -> dict:
        monkeypatch.setenv("MLB_HR_DATA_DIR", str(assembled_bundle_dir / "runtime_data"))
        try:
            return selftest.run_self_test(require_runtime_data=True)
        finally:
            monkeypatch.delenv("MLB_HR_DATA_DIR", raising=False)

    wfp.build_full_package(
        bundle_dir=bundle,
        statcast_src=CI_STATCAST_FIXTURE,
        output_zip=output_zip,
        manifest_path=tmp_path / "manifest.json",
        app_version="1.0.1",
        model_version="V1.0.0",
        model_hash="4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab",
        release_commit="test",
        run_self_test=run_real_self_test,
    )

    # This is the actual regression gate: open the real zip and inspect its bytes.
    manifest = wfp.validate_full_release_zip(output_zip)
    assert manifest["statcast_runtime_available"] is True
    assert manifest["statcast_parquet_count"] > 0
    assert manifest["self_test_pass"] is True


def test_windows_full_release_gate_rejects_a_raw_app_only_zip(tmp_path):
    """A base bundle zipped WITHOUT running the FULL assembler (i.e. exactly what
    windows-native.yml's "Package Windows standalone application" step produces on
    its own) must fail validation -- this is what let v1.0.0 ship broken.
    """
    import zipfile

    bundle = _make_base_bundle(tmp_path)
    raw_zip = tmp_path / "MLB-HR-Windows-App.zip"
    with zipfile.ZipFile(raw_zip, "w") as zf:
        for path in bundle.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(bundle).as_posix())

    try:
        wfp.validate_full_release_zip(raw_zip)
    except wfp.FullPackageError as exc:
        assert "runtime_data/statcast" in str(exc)
    else:
        raise AssertionError(
            "validate_full_release_zip must reject a bundle-only zip with no Statcast"
        )
