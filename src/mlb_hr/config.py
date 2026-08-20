from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import os


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str = "MLB HR"
    organization: str = "MLBHR"
    user_agent: str = "MLBHRDesktop/0.1 contact=local-user"
    mlb_base_url: str = "https://statsapi.mlb.com"
    savant_csv_url: str = "https://baseballsavant.mlb.com/statcast_search/csv"
    nws_base_url: str = "https://api.weather.gov"
    odds_base_url: str = "https://api.the-odds-api.com/v4"
    network_connect_timeout_s: float = 8.0
    network_read_timeout_s: float = 25.0
    network_write_timeout_s: float = 10.0
    network_pool_timeout_s: float = 5.0
    max_retries: int = 3
    retry_base_delay_s: float = 0.5
    max_response_bytes: int = 50 * 1024 * 1024
    lineup_ttl_far: timedelta = timedelta(minutes=5)
    lineup_ttl_near: timedelta = timedelta(seconds=60)
    weather_ttl_far: timedelta = timedelta(minutes=30)
    weather_ttl_near: timedelta = timedelta(minutes=10)
    odds_fresh: timedelta = timedelta(minutes=10)
    odds_warning: timedelta = timedelta(minutes=30)
    default_stake: float = 10.0
    paper_bankroll_initial: float = 1000.0
    demo_mode: bool = os.getenv("MLB_HR_DEMO", "0") == "1"


CONFIG = AppConfig()
