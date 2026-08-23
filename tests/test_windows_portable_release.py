from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launchers_pin_runtime_data_next_to_executable():
    launcher = (ROOT / 'packaging/windows/MLB HR.bat').read_text(encoding='utf-8')
    selftest = (ROOT / 'packaging/windows/SELF TEST.bat').read_text(encoding='utf-8')

    assert 'MLB_HR_DATA_DIR=%~dp0runtime_data' in launcher
    assert '%MLB_HR_DATA_DIR%\\statcast' in launcher
    assert 'app.exe' in launcher

    assert 'MLB_HR_DATA_DIR=%~dp0runtime_data' in selftest
    assert '--self-test --require-runtime-data' in selftest


def test_windows_workflow_packages_portable_launchers():
    workflow = (ROOT / '.github/workflows/windows-native.yml').read_text(encoding='utf-8')
    assert 'packaging\\windows\\MLB HR.bat' in workflow
    assert 'packaging\\windows\\SELF TEST.bat' in workflow
    assert 'MLB-HR-Windows-App.zip' in workflow


def test_full_release_assembler_requires_statcast_and_downloads_fresh_windows_artifact():
    assembler = (ROOT / 'scripts/create_windows_full_release.sh').read_text(encoding='utf-8')
    assert "find \"$STATCAST_SRC\" -type f -name 'statcast_*.parquet'" in assembler
    assert 'gh workflow run "$WORKFLOW" --ref "$BRANCH"' in assembler
    assert 'gh run watch "$RUN_ID" --exit-status' in assembler
    assert 'gh run download "$RUN_ID"' in assembler
    assert 'runtime_data/statcast' in assembler
    assert 'MLB-HR-Windows-V1.0.1-FULL.zip' in assembler
