from types import SimpleNamespace

from mlb_hr.domain.enums import ModelClassification
from mlb_hr.ui.presentation import practical_status, visible_cards


def test_practical_status_mapping():
    assert practical_status(ModelClassification.PRIMARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.SECONDARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.WATCH) == "VIGILAR"
    assert practical_status(ModelClassification.NO_BET) == "NO CUMPLE FILTRO"


def test_visible_cards_defaults_to_top_15():
    cards = [SimpleNamespace(prediction=SimpleNamespace(final_hr_probability=1 - i / 100)) for i in range(30)]
    assert len(visible_cards(cards, expanded=False)) == 15
    assert len(visible_cards(cards, expanded=True)) == 30
