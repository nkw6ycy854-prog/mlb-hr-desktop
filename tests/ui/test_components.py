from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.ui.components import ResponsiveGrid


def app():
    return QApplication.instance() or QApplication([])


def test_responsive_grid_switches_between_two_and_one_column():
    app()
    grid = ResponsiveGrid(two_column_min_width=760)
    grid.set_widgets([QLabel("A"), QLabel("B"), QLabel("C"), QLabel("D")])
    grid.resize(900, 400)
    grid.reflow()
    assert grid.column_count == 2
    grid.resize(600, 400)
    grid.reflow()
    assert grid.column_count == 1
