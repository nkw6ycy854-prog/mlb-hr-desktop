#!/usr/bin/env python3
"""Source-mode UI smoke check: sidebar navigation, all 3 screens render, resize at two sizes.

Run with QT_QPA_PLATFORM=offscreen. Prints a JSON report and exits nonzero on any
failure or unhandled exception, so it can gate CI/local verification.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class _FakeService:
    stake = 10.0


def main() -> int:
    result = {
        "sidebar_navigation": False,
        "today_render": False,
        "history_render": False,
        "settings_render": False,
        "resize_large": False,
        "resize_compact": False,
        "passed": False,
    }
    try:
        from PySide6.QtWidgets import QApplication

        from mlb_hr.resources_runtime import packaged_migrations_dir
        from mlb_hr.storage.sqlite import SQLiteStore
        from mlb_hr.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])

        with tempfile.TemporaryDirectory() as td:
            with packaged_migrations_dir() as migrations:
                store = SQLiteStore(Path(td) / "ui_smoke.db", migrations)
                store.migrate()

            window = MainWindow(_FakeService(), store)
            window.show()

            result["today_render"] = window.pages.currentIndex() == 0

            window.nav_history.click()
            result["history_render"] = window.pages.currentIndex() == 1

            window.nav_settings.click()
            result["settings_render"] = window.pages.currentIndex() == 2

            window.nav_today.click()
            result["sidebar_navigation"] = window.pages.currentIndex() == 0

            window.resize(1180, 760)
            result["resize_large"] = window.width() == 1180 and window.height() == 760

            window.resize(820, 700)
            result["resize_compact"] = window.width() == 820 and window.height() == 700

            window.close()

        result["passed"] = all(v for k, v in result.items() if k != "passed")
    except Exception as exc:
        result["error"] = str(exc)
        result["passed"] = False

    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
