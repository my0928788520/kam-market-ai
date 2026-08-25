"""Verified Paper Trading markers for futures chart overlays.

Markers are presentation-only records.  They cannot submit, confirm, or route an
order and deliberately carry fail-closed execution flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps


FUTURES_PAPER_MARKER_VERSION = "0.1"


class FuturesPaperMarkerAction(StrEnum):
    LONG_ENTRY = "long_entry"
    LONG_EXIT = "long_exit"
    SHORT_ENTRY = "short_entry"
    SHORT_COVER = "short_cover"


_ACTION_LABELS = {
    FuturesPaperMarkerAction.LONG_ENTRY: "多單進場",
    FuturesPaperMarkerAction.LONG_EXIT: "平多",
    FuturesPaperMarkerAction.SHORT_ENTRY: "空單進場",
    FuturesPaperMarkerAction.SHORT_COVER: "回補",
}


@dataclass(frozen=True, slots=True)
class FuturesPaperChartMarker:
    instrument: str
    occurred_at: datetime
    price: Decimal
    quantity: Decimal
    action: FuturesPaperMarkerAction
    source_event_hash: str
    source: str = "paper_trading_journal"
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("instrument must be a canonical futures symbol")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() != UTC.utcoffset(self.occurred_at):
            raise ValueError("occurred_at must be UTC timezone-aware")
        if not isinstance(self.price, Decimal) or not self.price.is_finite() or self.price <= 0:
            raise ValueError("price must be a finite positive Decimal")
        if not isinstance(self.quantity, Decimal) or not self.quantity.is_finite() or self.quantity <= 0:
            raise ValueError("quantity must be a finite positive Decimal")
        if not self.source_event_hash or not self.source:
            raise ValueError("verified Paper Trading source evidence is required")
        if (
            self.dry_run is not True
            or self.live_order_allowed is not False
            or self.broker_connected is not False
        ):
            raise ValueError("chart markers must remain Paper Trading only")

    @property
    def label(self) -> str:
        return _ACTION_LABELS[self.action]

    @property
    def marker_id(self) -> str:
        payload = dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"))
        return sha256(payload.encode("utf-8")).hexdigest()

    def canonical_payload(self) -> dict[str, object]:
        return {
            "version": FUTURES_PAPER_MARKER_VERSION,
            "instrument": self.instrument,
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "price": str(self.price),
            "quantity": str(self.quantity),
            "action": self.action.value,
            "label": self.label,
            "source_event_hash": self.source_event_hash,
            "source": self.source,
            "dry_run": True,
            "live_order_allowed": False,
            "broker_connected": False,
        }


def sort_futures_paper_markers(
    markers: tuple[FuturesPaperChartMarker, ...],
) -> tuple[FuturesPaperChartMarker, ...]:
    """Return deterministic chart order while rejecting duplicate evidence."""

    if not all(isinstance(marker, FuturesPaperChartMarker) for marker in markers):
        raise TypeError("all markers must be FuturesPaperChartMarker")
    hashes = tuple(marker.source_event_hash for marker in markers)
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate Paper Trading source event")
    return tuple(sorted(markers, key=lambda marker: (marker.occurred_at, marker.marker_id)))
