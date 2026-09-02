import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mlb_hr.domain.enums import (
    CombinationFilterStatus, ConfidenceLabel, CriticVerdict, IntegrityStatus, MarketPriceLabel,
    ModelClassification, ModelHealth, SlateQuality, UserActionLabel,
)
from mlb_hr.domain.models import (
    Combination, CombinationLeg, MarketDecision, PlayerRef, Prediction, PredictionCard,
    ProbabilityDistribution, SlateResult,
)
from mlb_hr.ui.combinations_page import CombinationsPageWidget


def app():
    return QApplication.instance() or QApplication([])


def _card(player_id, name, prob, classification=ModelClassification.PRIMARY, game_pk=1):
    player = PlayerRef(player_id, name)
    pitcher = PlayerRef(9000 + player_id, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{player_id}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="Yankees", opponent_name="Red Sox",
        game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc), final_hr_probability=prob,
        raw_hr_probability=prob, matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist, classification=classification,
        user_action=UserActionLabel.RECOMMENDED, integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=["Buen matchup", "Zona favorable"], main_risk="Bullpen fuerte", warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def _leg(player_id, name, prob, classification, game_pk=1):
    return CombinationLeg(f"pred-{player_id}", player_id, name, prob, classification, game_pk)


def _combo(kind, filter_status, legs, estimated_decimal_odds=None):
    return Combination(
        combination_id=f"combo-{kind}", kind=kind, legs=legs, model_probability_proxy=0.05,
        robustness=80.0, filter_status=filter_status, actual_parlay_american_odds=None,
        estimated_decimal_odds=estimated_decimal_odds, warnings=[],
    )


def _slate(cards, combos):
    return SlateResult(
        cards=cards, combinations=combos, slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=1, total_games=1, updated_at=datetime.now(timezone.utc),
    )


def test_all_four_kinds_always_visible_even_without_data():
    app()
    widget = CombinationsPageWidget(object())
    widget.render(_slate([], []))

    texts = "\n".join(l.text() for l in widget.findChildren(QLabel))
    for label in ("BEST 2-MAN", "BEST 3-MAN", "LONG-SHOT 2-MAN", "LONG-SHOT 3-MAN"):
        assert label in texts
    assert texts.count("NO HAY SUFICIENTES JUGADORES ANALIZADOS") == 4


def test_qualified_combo_gets_strong_visual_hierarchy():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.2, ModelClassification.PRIMARY), _leg(2, "B", 0.18, ModelClassification.SECONDARY)]
    cards = [_card(1, "A", 0.2), _card(2, "B", 0.18, ModelClassification.SECONDARY)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs, estimated_decimal_odds=3.2)
    widget.render(_slate(cards, [combo]))

    texts = "\n".join(l.text() for l in widget.findChildren(QLabel))
    assert "CUMPLE FILTRO" in texts


def test_fallback_combo_stays_visible_with_alto_riesgo_label():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.1, ModelClassification.WATCH), _leg(2, "B", 0.08, ModelClassification.NO_BET)]
    cards = [_card(1, "A", 0.1, ModelClassification.WATCH), _card(2, "B", 0.08, ModelClassification.NO_BET)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.FALLBACK, legs)
    widget.render(_slate(cards, [combo]))

    texts = "\n".join(l.text() for l in widget.findChildren(QLabel))
    assert "ALTO RIESGO" in texts and "NO CUMPLE FILTRO" in texts


def test_payout_shows_na_with_explanation_when_no_combined_odds():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.2, ModelClassification.PRIMARY), _leg(2, "B", 0.18, ModelClassification.SECONDARY)]
    cards = [_card(1, "A", 0.2), _card(2, "B", 0.18, ModelClassification.SECONDARY)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs, estimated_decimal_odds=None)
    widget.render(_slate(cards, [combo]))

    texts = "\n".join(l.text() for l in widget.findChildren(QLabel))
    assert "PAYOUT: N/A" in texts
    assert "SIN CUOTA CONJUNTA" in texts or "cuota" in texts.lower()


def test_clicking_combo_opens_detail_with_each_leg_and_global_info():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.2, ModelClassification.PRIMARY), _leg(2, "B", 0.18, ModelClassification.SECONDARY)]
    cards = [_card(1, "A", 0.2), _card(2, "B", 0.18, ModelClassification.SECONDARY)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs, estimated_decimal_odds=3.2)
    widget.render(_slate(cards, [combo]))

    widget._cards_by_kind["BEST_2_MAN"].detail_btn.click()

    assert widget.detail_panel.isHidden() is False
    body_texts = "\n".join(l.text() for l in widget.detail_panel.findChildren(QLabel))
    assert "A" in body_texts and "B" in body_texts


def test_clicking_a_leg_player_opens_player_detail_with_volver_button():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.2, ModelClassification.PRIMARY)]
    cards = [_card(1, "A", 0.2)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs)
    widget.render(_slate(cards, [combo]))
    widget._cards_by_kind["BEST_2_MAN"].detail_btn.click()

    player_btn = next(b for b in widget.detail_panel.findChildren(QPushButton) if "A" in b.text())
    player_btn.click()

    body_texts = "\n".join(l.text() for l in widget.detail_panel.findChildren(QLabel))
    buttons = [b.text() for b in widget.detail_panel.findChildren(QPushButton)]
    assert "Buen matchup" in body_texts  # real reason data, not reinterpreted
    assert "VOLVER A COMBINACIÓN" in buttons


def test_volver_a_combinacion_restores_the_combo_view():
    app()
    widget = CombinationsPageWidget(object())
    legs = [_leg(1, "A", 0.2, ModelClassification.PRIMARY), _leg(2, "B", 0.18, ModelClassification.SECONDARY)]
    cards = [_card(1, "A", 0.2), _card(2, "B", 0.18, ModelClassification.SECONDARY)]
    combo = _combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs)
    widget.render(_slate(cards, [combo]))
    widget._cards_by_kind["BEST_2_MAN"].detail_btn.click()
    player_btn = next(b for b in widget.detail_panel.findChildren(QPushButton) if "A" in b.text())
    player_btn.click()

    volver_btn = next(b for b in widget.detail_panel.findChildren(QPushButton) if b.text() == "VOLVER A COMBINACIÓN")
    volver_btn.click()

    body_texts = "\n".join(l.text() for l in widget.detail_panel.findChildren(QLabel))
    assert "A" in body_texts and "B" in body_texts


def test_actualizar_button_calls_refresh_callback_and_disables_itself():
    app()
    widget = CombinationsPageWidget(object())
    calls = []
    widget.refresh_callback = lambda: calls.append(1)

    widget.refresh_btn.click()

    assert calls == [1]
    assert widget.refresh_btn.isEnabled() is False


def test_rendering_a_new_slate_re_enables_the_actualizar_button():
    app()
    widget = CombinationsPageWidget(object())
    widget.refresh_btn.setEnabled(False)

    widget.render(_slate([], []))

    assert widget.refresh_btn.isEnabled() is True
