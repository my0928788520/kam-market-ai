"""Monitor whether a signal's original causes remain healthy."""
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

@dataclass(frozen=True, slots=True)
class CauseHealth:
    timestamp: datetime; healthy: bool; failed_causes: tuple[str,...]; correction_delay_seconds: float | None

class CauseHealthMonitor:
    def __init__(self) -> None: self._first_failure: datetime | None=None
    def evaluate(self, timestamp: datetime, causes: Mapping[str,bool], corrected_at: datetime | None=None) -> CauseHealth:
        failed=tuple(sorted(k for k,v in causes.items() if not v))
        if failed and self._first_failure is None: self._first_failure=timestamp
        delay=None
        if self._first_failure is not None and corrected_at is not None:
            delay=max(0.0,(corrected_at-self._first_failure).total_seconds())
        return CauseHealth(timestamp,not failed,failed,delay)

