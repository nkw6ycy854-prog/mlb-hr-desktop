# MLB HR Best US Odds + FanDuel Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the best available US sportsbook HR price plus FanDuel reference for each qualified player without allowing odds to affect the predictive model.

**Architecture:** Fetch all US bookmaker HR props in one event request, parse them into existing `OddsQuote` objects, keep `PredictionCard.market` as FanDuel for backward-compatible ledger semantics, and add `PredictionCard.best_market` for display. Ranking remains computed before odds.

**Tech Stack:** Python 3.13, The Odds API v4, httpx wrapper, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Odds remain post-model.
- `PredictionCard.market` remains FanDuel reference.
- `best_market` is display/comparison only.
- Sportsbooks with no valid HR outcome for the player are absent, not rendered as “SIN MERCADO”.
- If FanDuel is best, UI shows it once as `FanDuel · MEJOR CUOTA`.
- Do not change prediction ordering after fetching odds.

---

### Task 1: Parse all US sportsbook HR quotes

**Files:**
- Modify: `src/mlb_hr/providers/odds.py`
- Modify: `tests/test_market.py`
- Create: `tests/test_odds_provider.py`

- [ ] **Step 1: Write failing parser test**

Build one fake payload containing FanDuel + DraftKings, same player:
```python
quotes = _parse_quotes(payload, game, now)
assert {(q.bookmaker, q.american_odds) for q in quotes} == {
    ("FanDuel", 390),
    ("DraftKings", 430),
}
```

- [ ] **Step 2: Verify RED**

Expected: only FanDuel is parsed.

- [ ] **Step 3: Implement parser**

Remove the hardcoded FanDuel book filter. Set:
```python
bookmaker = str(book.get("title") or book.get("key") or "Unknown")
```

Keep existing player-name mapping, over/yes selection rule, point <= 0.5 rule, freshness, and market validation.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_odds_provider.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/providers/odds.py tests/test_odds_provider.py
git commit -m "feat: parse MLB HR quotes from all US books"
```

---

### Task 2: Fetch all US HR quotes in one cached call

**Files:**
- Modify: `src/mlb_hr/providers/odds.py`
- Extend: `tests/test_odds_provider.py`

**Interfaces:**
- `fetch_us_hr_quotes(game) -> ProviderResult[list[OddsQuote]]`
- `fetch_fanduel_hr_quotes(game)` becomes a filtered compatibility wrapper.

- [ ] **Step 1: Write failing HTTP-contract test**

Using a fake `HttpClient`, assert event odds request params include:
```python
{
    "regions": "us",
    "markets": "batter_home_runs",
    "oddsFormat": "american",
}
```
and do **not** include `bookmakers="fanduel"`.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Move current network logic into `fetch_us_hr_quotes`. Cache the all-book list by `game_pk`. Implement:
```python
def fetch_fanduel_hr_quotes(self, game):
    result = self.fetch_us_hr_quotes(game)
    return ProviderResult(
        [q for q in (result.data or []) if q.bookmaker.lower() == "fanduel"],
        result.meta,
        result.error_code,
        result.error_message,
        result.raw_reference,
    )
```
Use the exact `ProviderResult` constructor signature from `providers/base.py`.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_odds_provider.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/providers/odds.py tests/test_odds_provider.py
git commit -m "feat: fetch all US MLB HR prices"
```

---

### Task 3: Add best-market display state without changing FanDuel ledger semantics

**Files:**
- Modify: `src/mlb_hr/domain/models.py`
- Modify: `src/mlb_hr/services/analysis.py:228-286`
- Modify: `tests/test_market.py`
- Add: `tests/test_analysis_best_odds.py`

**Interfaces:**
- `PredictionCard.best_market: MarketDecision | None = None`

- [ ] **Step 1: Write failing selection test**

Given FanDuel +390 and DraftKings +430:
```python
assert card.market.quote.bookmaker == "FanDuel"
assert card.market.quote.american_odds == 390
assert card.best_market.quote.bookmaker == "DraftKings"
assert card.best_market.quote.american_odds == 430
assert card.prediction.final_hr_probability == original_probability
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Add optional field:
```python
best_market: MarketDecision | None = None
```

In analysis, for each game call `fetch_us_hr_quotes()` once. Group quotes by player. For each qualified card:
```python
player_quotes = by_player.get(player_id, [])
fanduel_quote = next((q for q in player_quotes if q.bookmaker.lower() == "fanduel"), None)
best_quote = max(
    (q for q in player_quotes if q.decimal_odds is not None),
    key=lambda q: q.decimal_odds,
    default=None,
)
card.market = self.market.evaluate(probability, fanduel_quote, self.stake)
card.best_market = self.market.evaluate(probability, best_quote, self.stake)
```

Persist all retrieved quotes with `is_at_prediction=False`; persist FanDuel again as `is_at_prediction=True` only for the existing reference ledger. Do not write best quote to `model_ledger`.

- [ ] **Step 4: Verify ranking isolation**

Add assertion that ranking before and after assigning odds is identical by prediction IDs.

Run:
```bash
pytest tests/test_analysis_best_odds.py tests/test_market.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/domain/models.py src/mlb_hr/services/analysis.py tests/test_analysis_best_odds.py tests/test_market.py
git commit -m "feat: attach best US price alongside FanDuel"
```

---

### Task 4: Render best quote + FanDuel without duplication

**Files:**
- Modify: `src/mlb_hr/ui/presentation.py`
- Modify: `src/mlb_hr/ui/today.py`
- Extend: `tests/ui/test_presentation.py`
- Extend: `tests/ui/test_today.py`

- [ ] **Step 1: Add failing display tests**

Assert:
- best DraftKings +430 + FanDuel +390 both visible;
- if best is FanDuel +430, detail contains one `FanDuel +430 · MEJOR CUOTA` line and no duplicate FanDuel line;
- missing non-FanDuel books are not rendered.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement display helper**

Return a small structure:
```python
@dataclass(frozen=True)
class QuoteDisplay:
    best_text: str
    fanduel_text: str | None
```

If best bookmaker is FanDuel, set `fanduel_text=None`.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_presentation.py tests/ui/test_today.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/presentation.py src/mlb_hr/ui/today.py tests/ui/test_presentation.py tests/ui/test_today.py
git commit -m "feat: show best sportsbook price and FanDuel reference"
```
