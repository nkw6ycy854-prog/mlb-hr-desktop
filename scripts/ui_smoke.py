#!/usr/bin/env python3
"""Source-mode UI smoke check for V1.1.0: sidebar navigation, HOY TOP 15/POR
PARTIDOS, canonical-time cross-surface consistency, all 3 HISTORIAL modes,
ACTUALIZAR RESULTADOS control, AJUSTES, resize at two sizes, and the
functional audit deliverable's presence/completeness.

Run with QT_QPA_PLATFORM=offscreen. Prints a JSON report and exits nonzero on
any failure or unhandled exception, so it can gate CI/local verification.
Uses deterministic fake data throughout -- no live network, no real DB.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GAME_TIME = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)  # -> 7:15 PM America/Santo_Domingo
CREATED_AT = GAME_TIME - timedelta(hours=3)
EXPECTED_TIME = "7:15 PM"


class _FakeService:
    stake = 10.0


class _FakeStore:
    def __init__(self) -> None:
        self._state = {"timezone_name": "America/Santo_Domingo"}
        self.player_rows = [{
            "prediction_id": "hit_main", "player_name": "Hunter Goodman",
            "game_time": GAME_TIME.isoformat(), "created_at": CREATED_AT.isoformat(),
            "classification": "PRIMARY", "final_probability": 0.148,
            "reference_stake": 10.0, "odds_at_prediction": 320,
            "actual_hr_binary": 1, "pnl_amount": 25.0,
            "game_pk": 1, "team_name": "Colorado Rockies", "opponent_name": "Atlanta Braves",
        }]
        legs = [{"prediction_id": "hit_main", "player_id": 1, "player_name": "Hunter Goodman",
                  "probability": 0.148, "classification": "PRIMARY", "game_pk": 1}]
        self.combo_rows = [{
            "combination_id": "combo1", "kind": "BEST_2_MAN", "created_at": CREATED_AT.isoformat(),
            "legs_json": json.dumps(legs), "filter_status": "QUALIFIED",
            "won": 1, "profit_loss": 30.0, "estimated_decimal_odds": 3.2,
        }]

    def history_prediction_rows(self, limit=2000):
        return list(self.player_rows)

    def history_combination_rows(self, limit=1000):
        return list(self.combo_rows)

    def prediction_rows_by_ids(self, ids):
        return {"hit_main": {"game_time": GAME_TIME.isoformat()}}

    def leg_settlements(self, ids):
        return {"hit_main": {"actual_hr_binary": 1}}

    def get_state(self, key, default=None):
        return self._state.get(key, default)

    def set_state(self, key, value):
        self._state[key] = value


def _build_slate_result():
    from mlb_hr.domain.enums import (
        ConfidenceLabel, CriticVerdict, GameState, IntegrityStatus, MarketPriceLabel,
        ModelClassification, ModelHealth, SlateQuality, UserActionLabel,
    )
    from mlb_hr.domain.models import (
        GameContext, LineupEntry, MarketDecision, PlayerRef, Prediction, PredictionCard,
        ProbabilityDistribution, SlateResult, TeamLineup, VenueRef,
    )

    def player(pid, name):
        return PlayerRef(pid, name)

    def entry(pid, name, order):
        return LineupEntry(player=player(pid, name), batting_order=order)

    def card(pid, name, game_pk, prob, classification):
        dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
        pred = Prediction(
            prediction_id=f"pred-{pid}", snapshot_id="snap", game_pk=game_pk,
            player=player(pid, name), opposing_pitcher=player(9000 + pid, "Opposing SP"),
            team_name="TEAM", opponent_name="OPP", game_time=GAME_TIME,
            final_hr_probability=prob, raw_hr_probability=prob, matchup_score=80, grade="B",
            reliability=90, confidence_score=80, confidence_label=ConfidenceLabel.HIGH,
            distribution=dist, classification=classification, user_action=UserActionLabel.RECOMMENDED,
            integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
            reasons=["Abridor vulnerable al HR"], main_risk=None, warnings=[],
            model_version="V1.0.0", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
        )
        return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))

    game1 = GameContext(
        game_pk=1, game_date=date(2026, 8, 30), game_time=GAME_TIME,
        away_team_id=1, away_team_name="Colorado Rockies", home_team_id=2, home_team_name="Atlanta Braves",
        venue=VenueRef(1, "Truist Park"), state=GameState.PREGAME,
        away_lineup=TeamLineup(team_id=1, team_name="Colorado Rockies", confirmed=True, entries=[
            entry(1, "Hunter Goodman", 1),
        ]),
        home_lineup=TeamLineup(team_id=2, team_name="Atlanta Braves", confirmed=True, entries=[
            entry(4, "Matt Olson", 1),
        ]),
        away_starter=player(500, "Away SP"), home_starter=player(501, "Home SP"),
    )
    game2 = GameContext(
        game_pk=2, game_date=date(2026, 8, 30), game_time=GAME_TIME,
        away_team_id=3, away_team_name="New York Yankees", home_team_id=4, home_team_name="Boston Red Sox",
        venue=VenueRef(2, "Fenway Park"), state=GameState.PREGAME,
        away_lineup=TeamLineup(team_id=3, team_name="New York Yankees", confirmed=True, entries=[]),
        home_lineup=TeamLineup(team_id=4, team_name="Boston Red Sox", confirmed=False, entries=[]),
        away_starter=player(502, "Away SP2"), home_starter=None,
    )
    cards = [
        card(1, "Hunter Goodman", 1, 0.148, ModelClassification.PRIMARY),
        card(4, "Matt Olson", 1, 0.161, ModelClassification.PRIMARY),
    ]
    return SlateResult(
        cards=cards, combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=1, total_games=2, updated_at=datetime.now(timezone.utc),
        pregame_games=2, game_contexts=(game1, game2),
    )


def main() -> int:
    result = {
        "sidebar_navigation": False,
        "today_top15": False,
        "today_by_games": False,
        "canonical_time": False,
        "history_players": False,
        "history_combinations": False,
        "history_hits_today": False,
        "update_results_control": False,
        "settings": False,
        "functional_audit": False,
        "resize_large": False,
        "resize_compact": False,
        "passed": False,
    }
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QLabel, QPushButton

        from mlb_hr.ui.main_window import MainWindow

        app = QApplication.instance() or QApplication([])

        store = _FakeStore()
        window = MainWindow(_FakeService(), store)
        window.show()
        slate = _build_slate_result()
        window.today._loaded(slate)
        app.processEvents()

        # HOY: TOP 15 default, POR PARTIDOS switch
        result["today_top15"] = window.today.view_stack.currentIndex() == 0
        window.today.by_games_btn.click()
        app.processEvents()
        result["today_by_games"] = window.today.view_stack.currentIndex() == 1

        # canonical time: the same GAME_TIME must render identically in POR
        # PARTIDOS and the ranking detail panel.
        por_partidos_texts = "\n".join(
            l.text() for l in window.today.games_page.findChildren(QLabel)
        ) + "\n".join(b.text() for b in window.today.games_page.findChildren(QPushButton))
        window.today.top15_btn.click()
        app.processEvents()
        window.today.table.selectRow(0)
        window.today._select_row(0, 0)
        app.processEvents()
        detail_texts = "\n".join(l.text() for l in window.today.detail.findChildren(QLabel))
        result["canonical_time"] = EXPECTED_TIME in por_partidos_texts and EXPECTED_TIME in detail_texts

        # HISTORIAL: three modes render with the deterministic data.
        window.nav_history.click()
        app.processEvents()
        result["history_players"] = (
            window.history.mode_stack.currentIndex() == 0
            and window.history.players_table.rowCount() == 1
        )
        window.history.combinations_btn.click()
        app.processEvents()
        result["history_combinations"] = (
            window.history.mode_stack.currentIndex() == 1
            and window.history.combinations_table.rowCount() == 1
        )
        window.history.hits_today_btn.click()
        app.processEvents()
        result["history_hits_today"] = window.history.mode_stack.currentIndex() == 2

        # ACTUALIZAR RESULTADOS actually triggers settlement_runner (real
        # wiring, not just a connected-but-dead signal).
        settlement_calls = []

        class _Settled:
            updated = 1

        def _fake_settlement_runner():
            settlement_calls.append(1)
            return _Settled()

        window.history.settlement_runner = _fake_settlement_runner
        window.history.refresh_results_btn.click()
        for _ in range(50):
            app.processEvents()
            QTest.qWait(20)
            if settlement_calls and window.history.refresh_results_btn.isEnabled():
                break
        result["update_results_control"] = (
            bool(settlement_calls)
            and "actualizados" in window.history.results_feedback.text().lower()
        )

        # AJUSTES renders with its known-fixed controls present.
        window.nav_settings.click()
        app.processEvents()
        settings = window.settings
        result["settings"] = (
            window.pages.currentIndex() == 2
            and hasattr(settings, "stake") and hasattr(settings, "stake_custom")
            and hasattr(settings, "timezone") and not hasattr(settings, "density")
        )

        window.nav_today.click()
        app.processEvents()
        result["sidebar_navigation"] = window.pages.currentIndex() == 0

        window.resize(1180, 760)
        result["resize_large"] = window.width() == 1180 and window.height() == 760

        window.resize(820, 700)
        result["resize_compact"] = window.width() == 820 and window.height() == 700

        window.close()

        audit_path = ROOT / "FUNCTIONAL_AUDIT_V1_1.md"
        if audit_path.exists():
            # Skip the legend line itself (it names "BLOCKED"/"UNKNOWN" as
            # possible Estado values, which isn't an actual finding); only
            # table rows (an actual `Estado` cell) count as a real hit.
            audit_lines = [
                line for line in audit_path.read_text(encoding="utf-8").splitlines()
                if "`Estado`:" not in line
            ]
            audit_text = "\n".join(audit_lines)
            result["functional_audit"] = "BLOCKED" not in audit_text and "UNKNOWN" not in audit_text

        result["passed"] = all(v for k, v in result.items() if k != "passed")
    except Exception as exc:
        result["error"] = str(exc)
        result["passed"] = False

    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
