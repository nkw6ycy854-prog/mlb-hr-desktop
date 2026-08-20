from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Generic, TypeVar

from mlb_hr.domain.models import ProviderMeta

T = TypeVar("T")


@dataclass(slots=True)
class ProviderResult(Generic[T]):
    data: T | None
    meta: ProviderMeta
    error_code: str | None = None
    error_message: str | None = None
    raw_reference: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.data is not None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
