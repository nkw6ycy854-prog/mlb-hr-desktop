# MLB HR V1.1.0 Time + POR PARTIDOS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one canonical timezone service and a POR PARTIDOS view that groups the existing slate by game/team without changing prediction outputs.

**Architecture:** Add `GameTimeService` for all game-time conversion and `GamePredictionViewBuilder` for immutable presentation read-models. `TodayWidget` switches between the existing global ranking and the new game-grouped view.

**Tech Stack:** Python 3.13, PySide6 6.11.x, zoneinfo, dataclasses, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-mlb-hr-v1-1-design.md`

## Global Constraints

- V1.0.1 Windows Statcast hotfix must already be verified.
- MODEL VERSION remains `V1.0.0`.
- MODEL HASH remains `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`.
- Default timezone exactly `America/Santo_Domingo`.
- No manual timezone offsets.
- A game with only one confirmed lineup is not READY.
- LIVE/FINAL never generate new predictions.
- No probability/classification/ranking changes.

---

### Task 1: Preflight repository contract

**Files:**
- Read only: `src/mlb_hr/**`, `scripts/**`, `.github/workflows/**`
- Create: `V1_1_PREFLIGHT.md`

- [ ] **Step 1: Verify V1.0.1 prerequisite**

```bash
git status --short
git rev-parse HEAD
git log --oneline -12
rg -n "1\.0\.1|require-runtime-data|statcast_runtime_available" src scripts .github tests pyproject.toml
```

If the verified runtime-data hotfix is absent, STOP.

- [ ] **Step 2: Map current symbols**

```bash
rg -n "class TodayWidget|class HistoryWidget|class SettingsWidget|class SlateResult|class PredictionCard|def analyze_slate|timezone_name|game_time" src tests
```

Write exact current paths/symbols into `V1_1_PREFLIGHT.md`.

- [ ] **Step 3: Verify frozen model**

Run existing self-test/manifest verification and record exact model version/hash.

- [ ] **Step 4: Commit report**

```bash
git add V1_1_PREFLIGHT.md
git commit -m "docs: record v1.1 preflight contract"
```

---

### Task 2: Canonical GameTimeService

**Files:**
- Create: `src/mlb_hr/services/game_time.py`
- Create: `tests/test_game_time.py`
- Modify: `src/mlb_hr/ui/presentation.py`
- Modify: `src/mlb_hr/storage/sqlite.py` only if the persisted default timezone differs.

**Interfaces:**
```python
class GameTimeService:
    DEFAULT_TIMEZONE = "America/Santo_Domingo"
    def __init__(self, timezone_name: str = DEFAULT_TIMEZONE): ...
    def localize(self, value: datetime) -> datetime: ...
    def format_time(self, value: datetime | None) -> str: ...
    def format_date(self, value: datetime | None) -> str: ...
```

- [ ] **Step 1: Write failing tests**

```python
from datetime import datetime, timezone
from mlb_hr.services.game_time import GameTimeService

def test_santo_domingo_default():
    svc = GameTimeService()
    dt = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)
    assert svc.timezone_name == "America/Santo_Domingo"
    assert svc.format_time(dt) == "7:15 PM"

def test_new_york_dst_is_zoneinfo_driven():
    svc = GameTimeService("America/New_York")
    summer = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)
    winter = datetime(2026, 12, 30, 23, 15, tzinfo=timezone.utc)
    assert svc.format_time(summer) == "7:15 PM"
    assert svc.format_time(winter) == "6:15 PM"
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_game_time.py -v
```

- [ ] **Step 3: Implement minimal service**

```python
from zoneinfo import ZoneInfo

class GameTimeService:
    DEFAULT_TIMEZONE = "America/Santo_Domingo"

    def __init__(self, timezone_name=DEFAULT_TIMEZONE):
        self.timezone_name = timezone_name
        self._zone = ZoneInfo(timezone_name)

    def localize(self, value):
        if value.tzinfo is None:
            raise ValueError("game_time must be timezone-aware")
        return value.astimezone(self._zone)

    def format_time(self, value):
        if value is None:
            return "—"
        text = self.localize(value).strftime("%I:%M %p")
        return text[1:] if text.startswith("0") else text
```

`format_date()` must use the same localized value.

- [ ] **Step 4: Route UI presentation through the service**

Remove duplicate game-time formatting/manual offsets from presentation helpers.

- [ ] **Step 5: Verify GREEN**

```bash
pytest tests/test_game_time.py tests/ui/test_presentation.py -v
pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/mlb_hr/services/game_time.py src/mlb_hr/ui/presentation.py src/mlb_hr/storage/sqlite.py tests/test_game_time.py
git commit -m "feat: centralize game timezone conversion"
```

---

### Task 3: Build game/team read-models

**Files:**
- Create: `src/mlb_hr/services/game_views.py`
- Create: `tests/test_game_views.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class PlayerGameView:
    player_id: int
    player_name: str
    hr_probability: float | None
    classification: str
    confidence: str
    practical_status: str
    eligible: bool
    card: object | None

@dataclass(frozen=True)
class TeamGameView:
    team_name: str
    lineup_confirmed: bool
    players: tuple[PlayerGameView, ...]

@dataclass(frozen=True)
class GamePredictionView:
    game_pk: int
    away: TeamGameView
    home: TeamGameView
    game_time_utc: datetime
    game_state: str
    ready: bool
    empty_message: str | None

class GamePredictionViewBuilder:
    def build(self, slate, timezone_name: str) -> tuple[GamePredictionView, ...]: ...
```

- [ ] **Step 1: Failing HR-order test**

Build cards out of order and assert each team's valid players are descending by probability.

- [ ] **Step 2: Failing one-lineup test**

```python
game = builder.build(slate_with_only_away_confirmed, "America/Santo_Domingo")[0]
assert game.ready is False
assert "ESPERANDO LINEUP" in game.empty_message
```

- [ ] **Step 3: Failing NOT_ELIGIBLE test**

Valid players sort first; an ineligible lineup player remains visible at bottom with probability `None`.

- [ ] **Step 4: Implement**

```python
ready = away.lineup_confirmed and home.lineup_confirmed and game_state == "PREGAME"
valid = sorted(valid_players, key=lambda p: p.hr_probability or -1, reverse=True)
players = tuple(valid + ineligible_players)
```

Never mutate `slate.cards`.

- [ ] **Step 5: Verify**

```bash
pytest tests/test_game_views.py -v
pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/mlb_hr/services/game_views.py tests/test_game_views.py
git commit -m "feat: add game-grouped prediction read models"
```

---

### Task 4: Add TOP 15 / POR PARTIDOS to HOY

**Files:**
- Modify: `src/mlb_hr/ui/today.py`
- Extend: `tests/ui/test_today.py`

**Interfaces:**
- `TodayWidget.top15_btn`
- `TodayWidget.by_games_btn`
- `TodayWidget.view_stack`
- `TodayWidget.render_game_views()`

- [ ] **Step 1: Failing switch test**

```python
widget._loaded(slate)
assert widget.view_stack.currentIndex() == 0
widget.by_games_btn.click()
assert widget.view_stack.currentIndex() == 1
widget.top15_btn.click()
assert widget.view_stack.currentIndex() == 0
```

- [ ] **Step 2: Failing content tests**

Require both teams, all lineup players, HR descending order, canonical time, and lineup state.

- [ ] **Step 3: Implement**

Keep current Top 15 in page 0. Add scrollable game cards in page 1. Selecting an eligible player reuses the existing detail handler.

- [ ] **Step 4: Empty-state tests**

Require distinct text for pending lineups, LIVE and FINAL.

- [ ] **Step 5: Verify**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_today.py tests/test_game_views.py tests/test_game_time.py -v
pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/mlb_hr/ui/today.py tests/ui/test_today.py
git commit -m "feat: add predictions grouped by game"
```

---

### Task 5: Use GameTimeService everywhere

**Files:**
- Modify: `src/mlb_hr/ui/history.py`
- Modify: `src/mlb_hr/ui/today.py`
- Modify: `src/mlb_hr/ui/presentation.py`
- Extend: `tests/ui/test_history.py`
- Extend: `tests/ui/test_today.py`

- [ ] **Step 1: Cross-surface failing test**

One fixed UTC game must render exactly `"7:15 PM"` in Top 15 detail, POR PARTIDOS, player history and combination history for `America/Santo_Domingo`.

- [ ] **Step 2: Remove duplicated game-time formatting**

```bash
rg -n "strftime|astimezone|timedelta\(hours|UTC-|UTC\+" src/mlb_hr/ui src/mlb_hr/services
```

Replace game-time formatting outside `GameTimeService`.

- [ ] **Step 3: Verify timezone change**

Persist a different `timezone_name`, refresh Today/History, and assert both use the new canonical time without rewriting historical UTC.

- [ ] **Step 4: Verify**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_today.py tests/ui/test_history.py tests/test_game_time.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/history.py src/mlb_hr/ui/today.py src/mlb_hr/ui/presentation.py tests/ui/test_history.py tests/ui/test_today.py
git commit -m "fix: use one game time source across UI"
```

## Plan 1 acceptance gate

```bash
pytest tests/test_game_time.py tests/test_game_views.py -v
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_today.py tests/ui/test_history.py -v
pytest -q
```

Stop and report before Plan 2.
