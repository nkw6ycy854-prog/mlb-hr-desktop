from datetime import date

from mlb_hr.providers.statcast import StatcastProvider


class _Probe(StatcastProvider):
    def __init__(self):
        self.calls = []

    def fetch_date_range(self, start, end, *, game_type="R"):
        self.calls.append((start, end, game_type))
        return "ok"


def test_fetch_day_delegates_to_single_day_range():
    p = _Probe()
    d = date(2024, 4, 1)
    assert p.fetch_day(d) == "ok"
    assert p.calls == [(d, d, "R")]


def test_training_runtime_declares_pandas_dependency():
    from pathlib import Path
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert '"pandas==2.3.3"' in pyproject
