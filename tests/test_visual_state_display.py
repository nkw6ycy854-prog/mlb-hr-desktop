from mlb_hr.ui.presentation import visual_state_display, visual_state_tooltip


def test_recomendado_has_icon_and_tone():
    icon, tone = visual_state_display("RECOMENDADO")
    assert icon and tone == "recomendado"


def test_vigilar_has_icon_and_tone():
    icon, tone = visual_state_display("VIGILAR")
    assert icon and tone == "vigilar"


def test_alto_riesgo_has_icon_and_tone():
    icon, tone = visual_state_display("ALTO RIESGO")
    assert icon and tone == "alto_riesgo"


def test_no_elegible_has_icon_and_tone():
    icon, tone = visual_state_display("NO ELEGIBLE")
    assert icon and tone == "no_elegible"


def test_all_four_icons_are_distinct():
    icons = {visual_state_display(s)[0] for s in ("RECOMENDADO", "VIGILAR", "ALTO RIESGO", "NO ELEGIBLE")}
    assert len(icons) == 4


def test_alto_riesgo_and_no_elegible_have_explanatory_tooltips():
    assert visual_state_tooltip("ALTO RIESGO")
    assert visual_state_tooltip("NO ELEGIBLE")


def test_recomendado_and_vigilar_need_no_tooltip():
    assert visual_state_tooltip("RECOMENDADO") is None
    assert visual_state_tooltip("VIGILAR") is None
