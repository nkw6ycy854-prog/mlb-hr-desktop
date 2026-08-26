from __future__ import annotations

import os
import sys


def main()->int:
    if "--self-test" in sys.argv:
        from mlb_hr.selftest import main as selftest_main
        return selftest_main()
    try:
        from PySide6.QtCore import QCoreApplication,QTimer,QThreadPool
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required. Install the pinned dependencies from pyproject.toml.",file=sys.stderr);return 2
    QCoreApplication.setOrganizationName("MLBHR");QCoreApplication.setApplicationName("MLB HR")
    app=QApplication(sys.argv)
    from mlb_hr.config import CONFIG
    from mlb_hr.services.bootstrap import build_services
    from mlb_hr.services.demo import DemoAnalysisService
    from mlb_hr.services.health import HealthService
    from mlb_hr.services.settlement import SettlementService
    from mlb_hr.ui.main_window import MainWindow
    from mlb_hr.ui.workers import FunctionWorker
    from mlb_hr.ui.style import APP_STYLESHEET
    app.setStyleSheet(APP_STYLESHEET)
    real_service,paths,store=build_services(demo=CONFIG.demo_mode)
    from mlb_hr.observability import configure_logging
    configure_logging(paths.log_dir)
    service=DemoAnalysisService(float(store.get_state("default_stake",10.0))) if CONFIG.demo_mode else real_service
    window=MainWindow(service,store,paths);window.show()

    def start_health():
        # Health checks always inspect the real service (package/analytics/odds), never the
        # demo-mode wrapper, which intentionally has no runtime dependencies of its own.
        worker=FunctionWorker(HealthService(real_service,paths,store).run)
        window._health_worker=worker
        worker.signals.finished.connect(window.apply_health_report)
        worker.signals.error.connect(window.apply_health_error)
        QThreadPool.globalInstance().start(worker)

    window.health_retry_callback=start_health
    QTimer.singleShot(50,start_health)
    if not CONFIG.demo_mode:
        # Result reconciliation runs off the UI thread and never changes predictive weights.
        def start_settlement_reconcile():
            worker=FunctionWorker(SettlementService(store).reconcile_pending)
            # Keep a Python reference until completion; QRunnable ownership is otherwise C++-side.
            window._settlement_worker=worker
            worker.signals.finished.connect(lambda _r: setattr(window,"_settlement_worker",None))
            worker.signals.error.connect(lambda _e: setattr(window,"_settlement_worker",None))
            QThreadPool.globalInstance().start(worker)
        QTimer.singleShot(2500,start_settlement_reconcile)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
