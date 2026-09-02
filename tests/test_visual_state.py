from mlb_hr.domain.enums import ModelClassification
from mlb_hr.ui.presentation import UNKNOWN_CLASSIFICATION_VISUAL_STATE, is_known_classification, visual_state


def test_primary_eligible_is_recomendado():
    assert visual_state(ModelClassification.PRIMARY, eligible=True) == "RECOMENDADO"


def test_secondary_eligible_is_recomendado():
    assert visual_state(ModelClassification.SECONDARY, eligible=True) == "RECOMENDADO"


def test_watch_eligible_is_vigilar():
    assert visual_state(ModelClassification.WATCH, eligible=True) == "VIGILAR"


def test_no_bet_eligible_is_alto_riesgo():
    assert visual_state(ModelClassification.NO_BET, eligible=True) == "ALTO RIESGO"


def test_not_eligible_is_no_elegible_regardless_of_classification():
    assert visual_state(ModelClassification.NOT_ELIGIBLE, eligible=False) == "NO ELEGIBLE"


def test_eligible_false_always_wins_even_with_a_primary_classification():
    # eligible=False is the absolute rule (approved plan): it must never be
    # overridden by classification, odds, filters, or UI state.
    assert visual_state(ModelClassification.PRIMARY, eligible=False) == "NO ELEGIBLE"


def test_unknown_classification_value_falls_back_to_alto_riesgo():
    assert visual_state("SOME_FUTURE_VALUE", eligible=True) == UNKNOWN_CLASSIFICATION_VISUAL_STATE
    assert UNKNOWN_CLASSIFICATION_VISUAL_STATE == "ALTO RIESGO"


def test_is_known_classification_reflects_the_five_real_enum_values():
    for c in (ModelClassification.PRIMARY, ModelClassification.SECONDARY, ModelClassification.WATCH,
              ModelClassification.NO_BET, ModelClassification.NOT_ELIGIBLE):
        assert is_known_classification(c) is True
    assert is_known_classification("SOME_FUTURE_VALUE") is False
