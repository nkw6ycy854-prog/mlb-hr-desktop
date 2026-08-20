from __future__ import annotations

from dataclasses import dataclass

from mlb_hr.domain.enums import RoofStatus
from mlb_hr.domain.models import VenueRef, WeatherSnapshot


@dataclass(slots=True)
class ParkEnvironmentResult:
    structural_factor: float
    handedness_factor: float
    geometry_fit: float
    park_fit_delta: float
    weather_index: float
    park_reliability: float
    environment_reliability: float
    reasons: list[str]
    warnings: list[str]


class ParkEnvironmentEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    def evaluate(self, venue: VenueRef, batter_hand: str | None, weather: WeatherSnapshot | None) -> ParkEnvironmentResult:
        factors = self.config.get("park_factors", {})
        v = factors.get(str(venue.venue_id), {}) if isinstance(factors, dict) else {}
        general = float(v.get("general", 1.0))
        hand_key = "L" if batter_hand == "L" else "R"
        hand_factor = float(v.get(hand_key, general))
        # Geometry fit is versioned in the model package. Without a trained venue-specific
        # geometry model it remains neutral rather than invented.
        geometry = float(v.get("geometry_default", 0.0))
        park_delta = (hand_factor - 1.0) + geometry
        park_rel = float(v.get("reliability", 0.55 if v else 0.25))
        reasons: list[str] = []
        warnings: list[str] = []
        if park_delta >= 0.04:
            reasons.append("Parque favorable para el perfil del bateador")
        elif park_delta <= -0.04:
            warnings.append("Parque menos favorable para HR")

        weather_index = 0.0
        env_rel = 0.25
        if weather is not None:
            env_rel = weather.reliability
            temp_coef = float(self.config.get("temperature_per_10f", 0.0))
            wind_coef = float(self.config.get("wind_out_per_10mph", 0.0))
            humidity_coef = float(self.config.get("humidity_per_20pct", 0.0))
            if weather.roof in {RoofStatus.CLOSED, RoofStatus.FIXED_DOME}:
                weather_index = 0.0
                env_rel = max(env_rel, 0.95)
            else:
                if weather.temperature_f is not None:
                    weather_index += ((weather.temperature_f - 72.0) / 10.0) * temp_coef
                if weather.wind_out_component is not None:
                    weather_index += (weather.wind_out_component / 10.0) * wind_coef
                if weather.humidity_pct is not None:
                    weather_index += ((weather.humidity_pct - 50.0) / 20.0) * humidity_coef
                cap = float(self.config.get("weather_cap", 0.12))
                weather_index = max(-cap, min(cap, weather_index))
                if weather_index >= 0.025:
                    reasons.append("Entorno climático favorable")
                elif weather_index <= -0.025:
                    warnings.append("Entorno climático desfavorable")
            warnings.extend(weather.warnings)
        return ParkEnvironmentResult(
            structural_factor=general,
            handedness_factor=hand_factor,
            geometry_fit=geometry,
            park_fit_delta=park_delta,
            weather_index=weather_index,
            park_reliability=park_rel,
            environment_reliability=env_rel,
            reasons=reasons,
            warnings=warnings,
        )
