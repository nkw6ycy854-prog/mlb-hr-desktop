from datetime import datetime, timezone

import pytest

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


def test_format_time_returns_em_dash_for_none():
    svc = GameTimeService()
    assert svc.format_time(None) == "—"


def test_format_date_uses_localized_value():
    svc = GameTimeService("America/New_York")
    dt = datetime(2026, 8, 31, 2, 30, tzinfo=timezone.utc)
    assert svc.format_date(dt) == svc.localize(dt).strftime("%Y-%m-%d")


def test_format_date_returns_em_dash_for_none():
    svc = GameTimeService()
    assert svc.format_date(None) == "—"


def test_localize_rejects_naive_datetime():
    svc = GameTimeService()
    with pytest.raises(ValueError):
        svc.localize(datetime(2026, 8, 30, 23, 15))


def test_localize_accepts_already_timezone_aware_utc():
    svc = GameTimeService("America/Santo_Domingo")
    dt = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)
    localized = svc.localize(dt)
    assert localized.utcoffset().total_seconds() == -4 * 3600
