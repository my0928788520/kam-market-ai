"""空明 KAM｜Observation Engine V0.1 — descriptive market observations only."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from ..models import Instrument, SessionKind
from ..session import SessionEngine


class ObservationDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    market: str
    instrument: Instrument
    symbol: str
    exchange_event_at: datetime | None
    received_at: datetime
    session: str
    price: float
    volume: int
    direction: ObservationDirection
    source: str
    observation_type: str
    created_at: datetime

    def payload(self) -> dict[str, object]:
        data = asdict(self)
        data["instrument"] = self.instrument.value
        data["direction"] = self.direction.value
        for name in ("exchange_event_at", "received_at", "created_at"):
            value = getattr(self, name)
            data[name] = value.isoformat() if value else None
        return data


@dataclass(frozen=True, slots=True)
class MappedMarketEvent:
    market: str
    instrument: Instrument
    symbol: str
    exchange_event_at: datetime | None
    received_at: datetime
    price: float
    volume: int
    source: str
    after_hours: bool | None = None


class ObservationFactory:
    """Creates observations from successfully mapped market data only."""

    def __init__(self, session_engine: SessionEngine | None = None) -> None:
        self._session_engine = session_engine or SessionEngine()
        self._previous: dict[tuple[Instrument, str], float] = {}

    def from_mapped_event(self, event: MappedMarketEvent | None) -> Observation | None:
        if event is None:
            return None
        key = (event.instrument, event.symbol)
        previous = self._previous.get(key)
        direction = ObservationDirection.UNKNOWN if previous is None else (
            ObservationDirection.UP if event.price > previous else
            ObservationDirection.DOWN if event.price < previous else ObservationDirection.FLAT
        )
        self._previous[key] = event.price
        session = self._session_engine.classify(event.exchange_event_at).value if event.exchange_event_at else "UNKNOWN"
        return Observation(
            observation_id=str(uuid4()), market=event.market, instrument=event.instrument, symbol=event.symbol,
            exchange_event_at=event.exchange_event_at, received_at=event.received_at, session=session,
            price=event.price, volume=event.volume, direction=direction, source=event.source,
            observation_type="MARKET_TICK", created_at=datetime.now(UTC),
        )

    def from_lifecycle_event(self, *_: object) -> None:
        """Lifecycle events are intentionally not observations."""
        return None
