# MLB HR UI Foundation + HOY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tabbed shell with a professional sidebar layout and rebuild HOY as a responsive Top-15-first screen with clear statuses, compact detail, working feedback, and no overlapping widgets.

**Architecture:** Keep `AnalysisService` and all prediction logic untouched. Introduce small presentation helpers and reusable PySide6 layout components, then compose them in `MainWindow` and `TodayWidget`. The UI reads existing `SlateResult` / `PredictionCard` objects only.

**Tech Stack:** Python 3.13, PySide6 6.11.1, pytest, `PySide6.QtTest`.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Do not edit model, calibration, thresholds, training, holdout, or feature code.
- Existing `AnalysisService.analyze_slate()` behavior remains unchanged in this plan.
- No new runtime dependency.
- Tests must run headless with `QT_QPA_PLATFORM=offscreen`.
- Top 15 is the default; VER TODOS toggles all analyzed cards.
- Practical statuses are exactly `RECOMENDADO`, `VIGILAR`, `NO CUMPLE FILTRO`.
- FanDuel is still the only live quote source in this plan; the “Mejor cuota” column may reuse FanDuel until the best-odds plan adds multi-book data.

---

### Task 1: Add headless Qt test harness and presentation helpers

**Files:**
- Create: `tests/ui/conftest.py`
- Create: `tests/ui/test_presentation.py`
- Create: `src/mlb_hr/ui/presentation.py`

**Interfaces:**
- Produces: `practical_status(classification) -> str`
- Produces: `display_quote(card, *, best: bool) -> str`
- Produces: `visible_cards(cards, expanded: bool, limit: int = 15) -> list[PredictionCard]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ui/conftest.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
```

```python
# tests/ui/test_presentation.py
from types import SimpleNamespace
from mlb_hr.domain.enums import ModelClassification
from mlb_hr.ui.presentation import practical_status, visible_cards

def test_practical_status_mapping():
    assert practical_status(ModelClassification.PRIMARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.SECONDARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.WATCH) == "VIGILAR"
    assert practical_status(ModelClassification.NO_BET) == "NO CUMPLE FILTRO"

def test_visible_cards_defaults_to_top_15():
    cards = [SimpleNamespace(prediction=SimpleNamespace(final_hr_probability=1-i/100)) for i in range(30)]
    assert len(visible_cards(cards, expanded=False)) == 15
    assert len(visible_cards(cards, expanded=True)) == 30
```

- [ ] **Step 2: Run tests and verify RED**

Run:
```bash
pytest tests/ui/test_presentation.py -v
```

Expected: FAIL because `mlb_hr.ui.presentation` does not exist.

- [ ] **Step 3: Implement minimal helpers**

```python
# src/mlb_hr/ui/presentation.py
from __future__ import annotations

from mlb_hr.domain.enums import ModelClassification

def practical_status(classification: ModelClassification) -> str:
    if classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY}:
        return "RECOMENDADO"
    if classification == ModelClassification.WATCH:
        return "VIGILAR"
    return "NO CUMPLE FILTRO"

def visible_cards(cards, *, expanded: bool, limit: int = 15):
    ordered = sorted(cards, key=lambda c: c.prediction.final_hr_probability, reverse=True)
    return ordered if expanded else ordered[:limit]

def display_quote(card, *, best: bool) -> str:
    market = getattr(card, "best_market", None) if best else None
    market = market or card.market
    quote = market.quote if market else None
    if not quote or quote.american_odds is None:
        return "—"
    return f"{quote.bookmaker} {quote.american_odds:+d}" if best else f"{quote.american_odds:+d}"
```

- [ ] **Step 4: Run tests and verify GREEN**

```bash
pytest tests/ui/test_presentation.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/ui/conftest.py tests/ui/test_presentation.py src/mlb_hr/ui/presentation.py
git commit -m "test: add UI presentation helpers"
```

---

### Task 2: Add reusable responsive UI components

**Files:**
- Create: `src/mlb_hr/ui/components.py`
- Create: `tests/ui/test_components.py`

**Interfaces:**
- Produces: `ResponsiveGrid(QWidget)` with `set_widgets(list[QWidget])` and public `column_count`.
- Produces: `StatusPill(QLabel)` with `set_status(text: str, tone: str)`.
- Produces: `make_scroll_page(content: QWidget) -> QScrollArea`.

- [ ] **Step 1: Write failing responsive-grid test**

```python
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
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/ui/test_components.py -v
```

Expected: FAIL because `ResponsiveGrid` does not exist.

- [ ] **Step 3: Implement components**

```python
# src/mlb_hr/ui/components.py
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

class StatusPill(QLabel):
    def set_status(self, text: str, tone: str = "muted") -> None:
        self.setText(text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)

class ResponsiveGrid(QWidget):
    def __init__(self, *, two_column_min_width: int = 760, parent=None):
        super().__init__(parent)
        self.two_column_min_width = two_column_min_width
        self.column_count = 1
        self._widgets = []
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)

    def set_widgets(self, widgets) -> None:
        self._widgets = list(widgets)
        self.reflow()

    def reflow(self) -> None:
        while self._layout.count():
            self._layout.takeAt(0)
        self.column_count = 2 if self.width() >= self.two_column_min_width else 1
        for i, widget in enumerate(self._widgets):
            self._layout.addWidget(widget, i // self.column_count, i % self.column_count)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow()

def make_scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area
```

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/ui/test_components.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/components.py tests/ui/test_components.py
git commit -m "feat: add responsive UI components"
```

---

### Task 3: Replace top tabs with sidebar + QStackedWidget

**Files:**
- Modify: `src/mlb_hr/ui/main_window.py:1-17`
- Create: `tests/ui/test_main_window.py`

**Interfaces:**
- `MainWindow.pages: QStackedWidget`
- `MainWindow.nav_today`, `nav_history`, `nav_settings`: checkable buttons
- `MainWindow.set_page(index: int)`

- [ ] **Step 1: Write navigation test**

```python
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import mlb_hr.ui.main_window as mw

class DummyPage(mw.QWidget):
    def refresh(self): self.refreshed = True

def test_sidebar_navigation_changes_page(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(mw, "TodayWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "HistoryWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "SettingsWidget", lambda *_: DummyPage())
    w = mw.MainWindow(object(), object())
    assert w.pages.currentIndex() == 0
    QTest.mouseClick(w.nav_history, Qt.MouseButton.LeftButton)
    assert w.pages.currentIndex() == 1
    QTest.mouseClick(w.nav_settings, Qt.MouseButton.LeftButton)
    assert w.pages.currentIndex() == 2
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/ui/test_main_window.py -v
```

Expected: FAIL because sidebar members do not exist.

- [ ] **Step 3: Implement sidebar shell**

Replace `QTabWidget` with:
- central `QWidget`
- horizontal layout
- fixed-width `QFrame` sidebar (190–210 px)
- three checkable navigation buttons
- `QStackedWidget`
- each page wrapped by `make_scroll_page`
- footer labels `Modelo`, `Datos`, package version.

Use `QButtonGroup(exclusive=True)` and connect each button to `set_page`.

- [ ] **Step 4: Verify navigation and full source tests**

```bash
pytest tests/ui/test_main_window.py -v
pytest -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/main_window.py tests/ui/test_main_window.py
git commit -m "feat: replace tabs with sidebar navigation"
```

---

### Task 4: Rebuild HOY header and Top 15 / VER TODOS table

**Files:**
- Modify: `src/mlb_hr/ui/today.py:17-96`
- Create: `tests/ui/test_today.py`

**Interfaces:**
- `TodayWidget.expanded: bool`
- `TodayWidget.toggle_all()`
- table columns exactly: `#`, `Jugador`, `HR%`, `Clasificación`, `Confianza`, `Mejor cuota`, `FanDuel`, `Estado`

- [ ] **Step 1: Write failing Top-15 test**

Create 20 `PredictionCard` values with monotonically descending probabilities, call `_loaded(SlateResult(...))`, and assert:
```python
assert widget.table.rowCount() == 15
assert widget.view_all_btn.text() == "VER TODOS"
widget.toggle_all()
assert widget.table.rowCount() == 20
assert widget.view_all_btn.text() == "VER TOP 15"
```

Also assert:
```python
assert widget.table.horizontalHeaderItem(7).text() == "Estado"
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/ui/test_today.py::test_today_defaults_to_top_15_and_can_expand -v
```

Expected: FAIL because `view_all_btn` / 8-column layout do not exist.

- [ ] **Step 3: Implement HOY header/table**

Use:
- title `HOY`
- `ACTUALIZAR` button on the right
- status line: model, data, games ready, updated time
- `MEJORES HR DEL DÍA` section + `VER TODOS`
- `visible_cards(self.current.cards, expanded=self.expanded)`
- 8 table columns from the spec
- `practical_status()` for final column
- `display_quote(card, best=True)` / `display_quote(card, best=False)` for the two quote columns.

Do not filter out `WATCH` or `NO_BET`; only `NOT_ELIGIBLE` rows may be omitted if they are not meant for display.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/ui/test_today.py -v
pytest -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/today.py tests/ui/test_today.py
git commit -m "feat: redesign today ranking table"
```

---

### Task 5: Compact player detail and explicit button feedback

**Files:**
- Modify: `src/mlb_hr/ui/today.py:98-131`
- Extend: `tests/ui/test_today.py`

**Interfaces:**
- `TodayWidget.copy_pick(card)`
- Copy button state: `COPIAR PICK` -> `COPIADO ✓` -> reset after 1500 ms.
- Manual odds control is visible only when a qualified player has no live FanDuel quote.

- [ ] **Step 1: Write failing copy-feedback test**

```python
widget._show_detail(card)
button = widget.copy_btn
button.click()
assert button.text() == "COPIADO ✓"
assert "HR" in QApplication.clipboard().text()
```

- [ ] **Step 2: Verify RED**

Expected: FAIL because the button is currently an anonymous local variable.

- [ ] **Step 3: Implement compact detail**

Persist labels/buttons as widget members. Show only:
- player
- `team vs opponent · time`
- HR probability
- classification + confidence
- best quote
- FanDuel
- up to 4 reasons
- main risk
- copy button.

Use `QTimer.singleShot(1500, ...)` to reset copy feedback.

Preserve manual quote support as a small fallback control only when:
```python
qualified = classification in {PRIMARY, SECONDARY}
missing_fanduel = card.market.quote is None
```
Otherwise hide it.

- [ ] **Step 4: Run tests**

```bash
pytest tests/ui/test_today.py -v
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/today.py tests/ui/test_today.py
git commit -m "feat: add compact player detail feedback"
```

---

### Task 6: Make HOY responsive and render combinations in a 2×2 responsive grid

**Files:**
- Modify: `src/mlb_hr/ui/today.py:22-146`
- Extend: `tests/ui/test_today.py`

**Interfaces:**
- `TodayWidget.main_pair: ResponsiveGrid`
- `TodayWidget.combo_grid: ResponsiveGrid`

- [ ] **Step 1: Write failing responsive test**

```python
widget.resize(1200, 800)
widget.main_pair.resize(1000, 500)
widget.main_pair.reflow()
widget.combo_grid.resize(1000, 400)
widget.combo_grid.reflow()
assert widget.main_pair.column_count == 2
assert widget.combo_grid.column_count == 2

widget.main_pair.resize(650, 500)
widget.combo_grid.resize(650, 600)
widget.main_pair.reflow()
widget.combo_grid.reflow()
assert widget.main_pair.column_count == 1
assert widget.combo_grid.column_count == 1
```

- [ ] **Step 2: Verify RED**

Expected: FAIL because current layouts are fixed horizontal rows.

- [ ] **Step 3: Implement responsive containers**

Put ranking table and detail card inside `ResponsiveGrid(two_column_min_width=980)`.
Put four combination cards inside `ResponsiveGrid(two_column_min_width=760)`.
Remove fixed detail maximum width; use minimum size + size policy.
Do not create horizontal scrollbars.

- [ ] **Step 4: Verify source suite**

```bash
pytest tests/ui/test_today.py tests/ui/test_components.py -v
pytest -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/today.py tests/ui/test_today.py
git commit -m "fix: make today layout responsive"
```

---

### Task 7: Refresh the stylesheet for sidebar, pills, cards, disabled feedback, and responsive density

**Files:**
- Modify: `src/mlb_hr/ui/style.py`
- Create: `tests/ui/test_style_contract.py`

- [ ] **Step 1: Add contract test**

Assert the stylesheet contains selectors for:
```python
for token in [
    "QFrame#sidebar",
    "QPushButton#navButton",
    'QPushButton#navButton:checked',
    'QLabel[tone="good"]',
    'QLabel[tone="warning"]',
    'QLabel[tone="bad"]',
    "QPushButton:disabled",
]:
    assert token in APP_STYLESHEET
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/ui/test_style_contract.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement stylesheet**

Keep the dark identity but use:
- clearer sidebar surface
- one accent for active nav / primary actions
- explicit disabled state
- compact table rows
- status pill tones
- consistent card radius/borders
- no `QTabWidget` selectors.

- [ ] **Step 4: Verify GREEN + all tests**

```bash
pytest tests/ui/test_style_contract.py -v
pytest -q
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/style.py tests/ui/test_style_contract.py
git commit -m "style: polish desktop UI shell"
```

## Plan acceptance evidence

Before moving to the combination plan:
```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui -v
pytest -q
```
Both commands must exit 0.
