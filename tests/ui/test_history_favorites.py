import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.resources_runtime import packaged_migrations_dir
from mlb_hr.services.favorites import FavoritesService
from mlb_hr.storage.sqlite import SQLiteStore
from mlb_hr.ui.history import HistoryWidget


def app():
    return QApplication.instance() or QApplication([])


def _store(tmp_path):
    with packaged_migrations_dir() as migrations_dir:
        s = SQLiteStore(tmp_path / "app.db", migrations_dir=migrations_dir)
        s.migrate()
    return s


def _save(svc, player_id=1, game_pk=100, **overrides):
    base = dict(
        player_id=player_id, game_pk=game_pk, player_name="Aaron Judge", team_name="Yankees",
        opponent_name="Red Sox", game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc),
        hr_probability=0.22, practical_status="RECOMENDADO", classification="PRIMARY",
        confidence_label="HIGH", eligible=True, best_bookmaker="DraftKings",
        best_american_odds=350, fanduel_american_odds=390, source_prediction_id="pred-1",
    )
    base.update(overrides)
    svc.save_favorite(**base)


def test_favoritos_tab_switches_to_fourth_stack_page(tmp_path):
    app()
    widget = HistoryWidget(_store(tmp_path))

    widget.favoritos_btn.click()

    assert widget.mode_stack.currentIndex() == 3


def test_favoritos_table_shows_saved_snapshot_row(tmp_path):
    app()
    store = _store(tmp_path)
    _save(FavoritesService(store))
    widget = HistoryWidget(store)

    widget.favoritos_btn.click()

    assert widget.favorites_table.rowCount() == 1
    assert widget.favorites_table.item(0, 1).text() == "Aaron Judge"
    assert widget.favorites_table.item(0, 3).text() == "22.0%"
    assert widget.favorites_table.item(0, 6).text() == "NO DISPONIBLE"


def test_favoritos_empty_state_message(tmp_path):
    app()
    widget = HistoryWidget(_store(tmp_path))

    widget.favoritos_btn.click()

    assert widget.empty_state_label.isHidden() is False
    assert "favoritos" in widget.empty_state_label.text().lower()


def test_favoritos_detail_shows_snapshot_and_resultado_final(tmp_path):
    app()
    store = _store(tmp_path)
    _save(FavoritesService(store))
    widget = HistoryWidget(store)
    widget.favoritos_btn.click()

    widget.favorites_table.cellClicked.emit(0, 0)

    texts = "\n".join(l.text() for l in widget.detail.findChildren(QLabel))
    assert "SNAPSHOT AL GUARDAR" in texts
    assert "RESULTADO FINAL" in texts
    assert "HR%: 22.0%" in texts


def test_favoritos_never_contributes_hit_rate_or_pnl_metrics(tmp_path):
    app()
    store = _store(tmp_path)
    _save(FavoritesService(store))
    widget = HistoryWidget(store)

    widget.favoritos_btn.click()

    metric_names = []
    for i in range(widget.metrics.count()):
        w = widget.metrics.itemAt(i).widget()
        if w:
            metric_names.extend(l.text() for l in w.findChildren(QLabel))
    assert not any("hit rate" in n.lower() for n in metric_names)
    assert not any("p/l" in n.lower() or "roi" in n.lower() for n in metric_names)


def test_favoritos_respects_period_filter(tmp_path):
    app()
    store = _store(tmp_path)
    svc = FavoritesService(store)
    _save(svc, player_id=1, game_pk=100)
    old_id = "old-fav"
    with store.transaction() as con:
        con.execute(
            """INSERT INTO favorites(
                favorite_id,player_id,game_pk,created_at,player_name,team_name,opponent_name,game_time,
                snapshot_hr_probability,snapshot_practical_status,snapshot_classification,
                snapshot_confidence_label,snapshot_eligible,snapshot_best_bookmaker,snapshot_best_american_odds,
                snapshot_fanduel_american_odds,source_prediction_id,operational_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
            (old_id, 2, 200, (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(),
             "Old Player", "Mets", "Braves", None, 0.1, "VIGILAR", "WATCH", "MEDIUM", 1, None, None, None, "pred-2"),
        )
    widget = HistoryWidget(store)

    widget.favoritos_btn.click()
    widget.period_buttons["30D"].click()

    assert widget.favorites_table.rowCount() == 1
    assert widget.favorites_table.item(0, 1).text() == "Aaron Judge"
