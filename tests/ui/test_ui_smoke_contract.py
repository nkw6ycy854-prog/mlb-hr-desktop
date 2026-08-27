import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ui_smoke_script_passes_all_checks():
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ui_smoke.py")],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    for key in (
        "sidebar_navigation",
        "today_render",
        "history_render",
        "settings_render",
        "resize_large",
        "resize_compact",
        "passed",
    ):
        assert payload[key] is True, f"{key} was not True: {payload}"
