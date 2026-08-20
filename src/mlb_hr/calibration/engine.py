from __future__ import annotations

from bisect import bisect_right

from mlb_hr.domain.math import clamp, logistic, logit


class CalibrationEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {"method": "none"}

    def calibrate(self, raw_probability: float) -> float:
        p = clamp(raw_probability, 1e-8, 1 - 1e-8)
        method = str(self.config.get("method", "none")).lower()
        if method == "none":
            return p
        if method in {"platt", "logistic"}:
            a = float(self.config.get("a", 1.0))
            b = float(self.config.get("b", 0.0))
            return clamp(logistic(a * logit(p) + b), 0.0, 1.0)
        if method == "isotonic":
            xs = [float(x) for x in self.config.get("x", [])]
            ys = [float(y) for y in self.config.get("y", [])]
            if not xs or len(xs) != len(ys):
                return p
            if p <= xs[0]:
                return ys[0]
            if p >= xs[-1]:
                return ys[-1]
            i = bisect_right(xs, p) - 1
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[i], ys[i + 1]
            t = (p - x0) / max(x1 - x0, 1e-12)
            return clamp(y0 + t * (y1 - y0), 0.0, 1.0)
        raise ValueError(f"Unsupported calibration method: {method}")
