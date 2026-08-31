from __future__ import annotations

from dataclasses import dataclass

from mlb_hr.services.settlement import SettlementService


@dataclass(frozen=True)
class SettlementRunResult:
    checked: int
    updated: int
    still_pending: int
    errors: tuple[str, ...]


class SettlementCoordinator:
    """Thin, idempotent wrapper around SettlementService.reconcile_pending().

    The underlying service already enforces idempotency at three layers
    (pending_predictions()/pending_combinations() exclude terminal rows,
    settlements are append-only/versioned, and apply_paper_settlement() has
    an explicit existence guard) -- see V1_1_SETTLEMENT_CONTRACT.md. This
    coordinator adds no new settlement logic; it only calls that existing
    entry point and reshapes its stats. It never calls analyze_slate() or
    anything that recomputes predictive output.
    """

    def __init__(self, settlement_service: SettlementService) -> None:
        self.settlement_service = settlement_service

    def refresh_pending(self) -> SettlementRunResult:
        stats = self.settlement_service.reconcile_pending()
        errors: tuple[str, ...] = ()
        if stats.get("errors"):
            errors = (f"{stats['errors']} predicción(es) sin feed de MLB disponible",)
        return SettlementRunResult(
            checked=stats.get("checked", 0),
            updated=stats.get("settled", 0),
            still_pending=stats.get("waiting", 0) + stats.get("review", 0),
            errors=errors,
        )
