from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from .enums import (
    CombinationFilterStatus,
    ConfidenceLabel,
    CriticVerdict,
    DataFreshness,
    GameState,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    ModelHealth,
    PlayerAppearanceStatus,
    RoofStatus,
    SettlementStatus,
    SlateQuality,
    UserActionLabel,
    WarningSeverity,
)


@dataclass(slots=True)
class ProviderMeta:
    provider: str
    fetched_at: datetime
    source_timestamp: datetime | None = None
    freshness: DataFreshness = DataFreshness.UNKNOWN
    complete: bool = True
    warnings: list[str] = field(default_factory=list)
    provider_version: str = "1"


@dataclass(slots=True)
class DataWarning:
    code: str
    severity: WarningSeverity
    message: str
    component: str = ""


@dataclass(slots=True)
class PlayerRef:
    player_id: int
    full_name: str
    bat_side: str | None = None
    throw_side: str | None = None
    team_id: int | None = None


@dataclass(slots=True)
class VenueRef:
    venue_id: int
    name: str
    latitude: float | None = None
    longitude: float | None = None
    orientation_deg: float | None = None
    roof: RoofStatus = RoofStatus.UNKNOWN
    config_version: str = "unknown"


@dataclass(slots=True)
class LineupEntry:
    player: PlayerRef
    batting_order: int
    position: str | None = None
    confirmed: bool = True


@dataclass(slots=True)
class TeamLineup:
    team_id: int
    team_name: str
    entries: list[LineupEntry] = field(default_factory=list)
    confirmed: bool = False


@dataclass(slots=True)
class GameContext:
    game_pk: int
    game_date: date
    game_time: datetime | None
    away_team_id: int
    away_team_name: str
    home_team_id: int
    home_team_name: str
    venue: VenueRef
    away_team_abbr: str | None = None
    home_team_abbr: str | None = None
    state: GameState = GameState.UNKNOWN
    away_lineup: TeamLineup | None = None
    home_lineup: TeamLineup | None = None
    away_starter: PlayerRef | None = None
    home_starter: PlayerRef | None = None
    fetched_at: datetime | None = None
    raw_status: str | None = None


@dataclass(slots=True)
class WeatherSnapshot:
    game_pk: int
    temperature_f: float | None = None
    wind_mph: float | None = None
    wind_direction_deg: float | None = None
    wind_text: str | None = None
    humidity_pct: float | None = None
    precip_probability_pct: float | None = None
    roof: RoofStatus = RoofStatus.UNKNOWN
    observed_at: datetime | None = None
    fetched_at: datetime | None = None
    reliability: float = 0.5
    wind_out_component: float | None = None
    wind_cross_component: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MetricValue:
    value: float | None
    sample_size: float = 0.0
    effective_sample_size: float = 0.0
    reliability: float = 0.0
    source: str = ""


@dataclass(slots=True)
class PlayerHistory:
    player_id: int
    pa: int = 0
    bbe: int = 0
    hr: int = 0
    hr_pa: float = 0.0
    barrel_rate: float = 0.0
    hardhit_rate: float = 0.0
    sweetspot_rate: float = 0.0
    avg_ev: float = 0.0
    max_ev: float = 0.0
    avg_launch_angle: float = 0.0
    flyball_rate: float = 0.0
    xslg: float = 0.0
    xwoba: float = 0.0
    k_rate: float = 0.0
    bb_rate: float = 0.0
    split_hr_pa: float = 0.0
    recent_30_hr_pa: float = 0.0
    recent_60_hr_pa: float = 0.0
    reliability: float = 0.0
    history_class: str = "MINIMAL_HISTORY"
    evidence_diversity: float = 0.0


@dataclass(slots=True)
class PitcherHistory:
    player_id: int
    bf: int = 0
    bbe: int = 0
    hr: int = 0
    hr_bf: float = 0.0
    barrel_allowed: float = 0.0
    hardhit_allowed: float = 0.0
    avg_ev_allowed: float = 0.0
    xslg_allowed: float = 0.0
    xwoba_allowed: float = 0.0
    fb_rate_allowed: float = 0.0
    split_hr_bf: float = 0.0
    recent_30_hr_bf: float = 0.0
    recent_60_hr_bf: float = 0.0
    avg_velocity: float = 0.0
    reliability: float = 0.0


@dataclass(slots=True)
class FeatureVector:
    batter_id: int
    pitcher_id: int
    game_pk: int
    values: dict[str, float]
    reliabilities: dict[str, float] = field(default_factory=dict)
    warnings: list[DataWarning] = field(default_factory=list)
    snapshot_id: str = ""


@dataclass(slots=True)
class ProbabilityDistribution:
    point: float
    p10: float
    p50: float
    p90: float
    interval_width: float
    stability_score: float


@dataclass(slots=True)
class Prediction:
    prediction_id: str
    snapshot_id: str
    game_pk: int
    player: PlayerRef
    opposing_pitcher: PlayerRef
    team_name: str
    opponent_name: str
    game_time: datetime | None
    final_hr_probability: float
    raw_hr_probability: float
    matchup_score: float
    grade: str
    reliability: float
    confidence_score: float
    confidence_label: ConfidenceLabel
    distribution: ProbabilityDistribution
    classification: ModelClassification
    user_action: UserActionLabel
    integrity: IntegrityStatus
    critic: CriticVerdict
    reasons: list[str]
    main_risk: str | None
    warnings: list[DataWarning]
    model_version: str
    feature_version: str
    calibration_version: str
    quality_gate_version: str
    model_health: ModelHealth = ModelHealth.GREEN
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def new_id() -> str:
        return str(uuid4())


@dataclass(slots=True)
class OddsQuote:
    game_pk: int
    player_id: int
    bookmaker: str
    market: str
    american_odds: int | None
    decimal_odds: float | None
    implied_probability: float | None
    last_update: datetime | None
    fetched_at: datetime
    freshness: DataFreshness
    source: str
    point: float | None = None
    selection_name: str | None = None


@dataclass(slots=True)
class MarketDecision:
    quote: OddsQuote | None
    label: MarketPriceLabel
    edge_pp: float | None = None
    expected_value_per_dollar: float | None = None
    payout_total: float | None = None
    profit: float | None = None


@dataclass(slots=True)
class PredictionCard:
    prediction: Prediction
    market: MarketDecision
    best_market: MarketDecision | None = None


@dataclass(slots=True)
class CombinationLeg:
    prediction_id: str
    player_id: int
    player_name: str
    probability: float
    classification: ModelClassification
    game_pk: int


@dataclass(slots=True)
class Combination:
    combination_id: str
    kind: str
    legs: list[CombinationLeg]
    model_probability_proxy: float
    robustness: float
    filter_status: CombinationFilterStatus
    actual_parlay_american_odds: int | None = None
    estimated_decimal_odds: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SlateResult:
    cards: list[PredictionCard]
    combinations: list[Combination]
    slate_quality: SlateQuality
    model_health: ModelHealth
    confirmed_lineups: int
    total_games: int
    updated_at: datetime
    pregame_games: int = 0
    live_games: int = 0
    final_games: int = 0
    messages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ResultRecord:
    prediction_id: str
    game_pk: int
    player_id: int
    status: SettlementStatus
    actual_hr_count: int | None = None
    actual_hr_binary: int | None = None
    actual_pa: int | None = None
    actual_pa_vs_starter: int | None = None
    actual_pa_vs_bullpen: int | None = None
    appearance_status: PlayerAppearanceStatus = PlayerAppearanceStatus.UNKNOWN
    verified_pbp: bool = False
    verified_box: bool = False
    result_version: int = 1
    result_source: str = "MLB"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    change_reason: str | None = None


@dataclass(slots=True)
class ModelPackageManifest:
    model_version: str
    feature_version: str
    calibration_version: str
    quality_gate_version: str
    model_type: str
    release_ready: bool
    training_cutoff: str | None
    validation_periods: list[str]
    holdout_period: str | None
    feature_names: list[str]
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    coefficients: dict[str, float]
    intercept: float
    calibration: dict[str, Any]
    thresholds: dict[str, Any]
    uncertainty: dict[str, Any]
    versions: dict[str, str]
    deterministic_seed: int = 20260817
    package_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
