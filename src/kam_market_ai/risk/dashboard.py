"""Updateable margin data and Shadow capital-risk snapshots."""
from dataclasses import dataclass
from datetime import datetime
from ..models import Instrument

@dataclass(frozen=True, slots=True)
class MarginRecord:
    instrument: Instrument; initial_margin: float; maintenance_margin: float; effective_at: datetime; source: str
class MarginCatalog:
    def __init__(self) -> None: self._records: dict[Instrument,MarginRecord]={}
    def update(self, record: MarginRecord) -> None:
        if record.initial_margin <= 0 or record.maintenance_margin <= 0: raise ValueError("margin must be positive")
        self._records[record.instrument]=record
    def get(self, instrument: Instrument) -> MarginRecord | None: return self._records.get(instrument)

@dataclass(frozen=True, slots=True)
class RiskSnapshot:
    capital: float; reserved_margin: float; risk_amount: float; risk_percent: float; margin_available: bool
class RiskDashboard:
    def __init__(self, margins: MarginCatalog) -> None: self.margins=margins
    def snapshot(self, capital: float, instrument: Instrument, entry: float, stop: float,
                 point_value: float, quantity: int=1) -> RiskSnapshot:
        if capital <= 0: raise ValueError("capital must be positive")
        record=self.margins.get(instrument); risk=abs(entry-stop)*point_value*quantity
        return RiskSnapshot(capital,record.initial_margin*quantity if record else 0.0,risk,risk/capital*100,record is not None)

