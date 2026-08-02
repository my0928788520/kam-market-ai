"""Descriptive cross-market reaction analysis without trading semantics.

The first exchange-timestamped event in a cluster is an ordering anchor only.
It does not establish causality, a market leader, or a prediction.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from statistics import median
from typing import Iterable

from ..models import Instrument


class PriceDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class ReactionClass(StrEnum):
    FULL_FOLLOW = "FULL_FOLLOW"
    PARTIAL_FOLLOW = "PARTIAL_FOLLOW"
    NO_FOLLOW = "NO_FOLLOW"
    OPPOSITE_RESPONSE = "OPPOSITE_RESPONSE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AlignmentType(StrEnum):
    TRANSIENT_ALIGNMENT = "TRANSIENT_ALIGNMENT"
    PERSISTENT_ALIGNMENT = "PERSISTENT_ALIGNMENT"
    PARTIAL_ALIGNMENT = "PARTIAL_ALIGNMENT"
    DIVERGENCE = "DIVERGENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ClusterEvent:
    """One normalized price observation.

    ``exchange_event_at`` is deliberately independent from ``received_at``.
    ``baseline_price`` is the preceding same-instrument price supplied by the
    ingestion layer; it is never inferred from another instrument's scale.
    """

    instrument: Instrument
    price: float
    baseline_price: float | None
    exchange_event_at: datetime | None
    received_at: datetime

    @property
    def change_bps(self) -> float | None:
        if self.baseline_price is None or self.baseline_price == 0:
            return None
        return (self.price - self.baseline_price) / self.baseline_price * 10_000

    @property
    def direction(self) -> PriceDirection | None:
        change = self.change_bps
        if change is None:
            return None
        if change > 0:
            return PriceDirection.UP
        if change < 0:
            return PriceDirection.DOWN
        return PriceDirection.FLAT


@dataclass(frozen=True, slots=True)
class EventCluster:
    """Events ordered by exchange timestamp, never by KAM receive timestamp."""

    events: tuple[ClusterEvent, ...]

    @classmethod
    def from_events(cls, events: Iterable[ClusterEvent]) -> "EventCluster":
        supplied = tuple(events)
        # Missing exchange time is ordered after timestamped observations while
        # retaining supplied order among ties. Receive time is never a fallback.
        ordered = tuple(sorted(
            enumerate(supplied),
            key=lambda item: (item[1].exchange_event_at is None, item[1].exchange_event_at, item[0]),
        ))
        return cls(tuple(event for _, event in ordered))


@dataclass(frozen=True, slots=True)
class ResponseWindow:
    response_within_100ms: bool | None
    response_within_250ms: bool | None
    response_within_500ms: bool | None
    response_within_1s: bool | None
    response_within_3s: bool | None
    response_within_5s: bool | None


@dataclass(frozen=True, slots=True)
class ReactionAnalysis:
    trigger_instrument: Instrument | None
    trigger_direction: PriceDirection | None
    trigger_event_at: datetime | None
    response_order: tuple[Instrument, ...]
    ir_response_direction: PriceDirection | None
    tx_response_direction: PriceDirection | None
    tmf_response_direction: PriceDirection | None
    ir_response_latency_ms: float | None
    tx_response_latency_ms: float | None
    tmf_response_latency_ms: float | None
    ir_response_change_bps: float | None
    tx_response_change_bps: float | None
    tmf_response_change_bps: float | None
    reaction_class: ReactionClass
    response_windows: ResponseWindow
    persist_1s: bool | None
    persist_3s: bool | None
    persist_5s: bool | None
    persist_10s: bool | None
    alignment_type: AlignmentType

    def storage_payload(self) -> dict[str, object]:
        """JSON-friendly descriptive payload for the observation store."""
        payload = asdict(self)
        for key in ("trigger_instrument", "trigger_direction", "reaction_class", "alignment_type"):
            value = payload.get(key)
            if hasattr(value, "value"):
                payload[key] = value.value
        payload["trigger_event_at"] = self.trigger_event_at.isoformat() if self.trigger_event_at else None
        return payload


class ReactionChainEngine:
    """Computes normalized descriptive response fields for one event cluster."""

    _instruments = (Instrument.TAIEX, Instrument.TX, Instrument.MTX)

    def analyze(self, cluster: EventCluster) -> ReactionAnalysis:
        if not cluster.events:
            return self._insufficient()
        trigger = cluster.events[0]
        responses = {instrument: self._response_for(cluster, trigger, instrument) for instrument in self._instruments}
        latencies = self._latencies(trigger, responses)
        response_order = tuple(
            event.instrument for event in cluster.events
            if event is not trigger and event.exchange_event_at is not None and trigger.exchange_event_at is not None
            and event.exchange_event_at >= trigger.exchange_event_at
        )
        reaction_class = self._classify(trigger, responses)
        persistence = tuple(self._persistence(cluster, trigger, responses, seconds) for seconds in (1, 3, 5, 10))
        return ReactionAnalysis(
            trigger_instrument=trigger.instrument,
            trigger_direction=trigger.direction,
            trigger_event_at=trigger.exchange_event_at,
            response_order=response_order,
            ir_response_direction=self._direction(responses[Instrument.TAIEX]),
            tx_response_direction=self._direction(responses[Instrument.TX]),
            tmf_response_direction=self._direction(responses[Instrument.MTX]),
            ir_response_latency_ms=latencies[Instrument.TAIEX],
            tx_response_latency_ms=latencies[Instrument.TX],
            tmf_response_latency_ms=latencies[Instrument.MTX],
            ir_response_change_bps=self._change(responses[Instrument.TAIEX]),
            tx_response_change_bps=self._change(responses[Instrument.TX]),
            tmf_response_change_bps=self._change(responses[Instrument.MTX]),
            reaction_class=reaction_class,
            response_windows=self._windows(responses, trigger),
            persist_1s=persistence[0], persist_3s=persistence[1],
            persist_5s=persistence[2], persist_10s=persistence[3],
            alignment_type=self._alignment(reaction_class, persistence),
        )

    def _response_for(self, cluster: EventCluster, trigger: ClusterEvent, instrument: Instrument) -> ClusterEvent | None:
        if instrument is trigger.instrument:
            return trigger
        if trigger.exchange_event_at is None:
            return None
        return next((event for event in cluster.events if event.instrument is instrument
                     and event.exchange_event_at is not None and event.exchange_event_at > trigger.exchange_event_at), None)

    @staticmethod
    def _direction(event: ClusterEvent | None) -> PriceDirection | None:
        return event.direction if event else None

    @staticmethod
    def _change(event: ClusterEvent | None) -> float | None:
        return event.change_bps if event else None

    def _latencies(self, trigger: ClusterEvent, responses: dict[Instrument, ClusterEvent | None]) -> dict[Instrument, float | None]:
        if trigger.exchange_event_at is None:
            return {instrument: None for instrument in self._instruments}
        result: dict[Instrument, float | None] = {}
        for instrument, event in responses.items():
            if event is None or event.exchange_event_at is None:
                result[instrument] = None
            else:
                result[instrument] = (event.exchange_event_at - trigger.exchange_event_at).total_seconds() * 1000
        return result

    def _classify(self, trigger: ClusterEvent, responses: dict[Instrument, ClusterEvent | None]) -> ReactionClass:
        trigger_direction = trigger.direction
        if trigger_direction is None or trigger_direction is PriceDirection.FLAT or trigger.exchange_event_at is None:
            return ReactionClass.INSUFFICIENT_DATA
        other = [event for instrument, event in responses.items() if instrument is not trigger.instrument]
        if any(event is None or event.direction is None for event in other):
            return ReactionClass.INSUFFICIENT_DATA
        directions = [event.direction for event in other if event is not None]
        if any(direction is not PriceDirection.FLAT and direction is not trigger_direction for direction in directions):
            return ReactionClass.OPPOSITE_RESPONSE
        follows = sum(direction is trigger_direction for direction in directions)
        if follows == len(directions):
            return ReactionClass.FULL_FOLLOW
        if follows:
            return ReactionClass.PARTIAL_FOLLOW
        return ReactionClass.NO_FOLLOW

    def _windows(self, responses: dict[Instrument, ClusterEvent | None], trigger: ClusterEvent | None = None) -> ResponseWindow:
        # This overload is resolved in analyze after obtaining exchange-only latency.
        if trigger is None:
            return ResponseWindow(None, None, None, None, None, None)
        latencies = self._latencies(trigger, responses)
        observed = [value for value in latencies.values() if value is not None]
        def within(milliseconds: float) -> bool | None:
            return all(value <= milliseconds for value in observed) if observed and len(observed) == 3 else None
        return ResponseWindow(within(100), within(250), within(500), within(1_000), within(3_000), within(5_000))

    def _persistence(self, cluster: EventCluster, trigger: ClusterEvent, responses: dict[Instrument, ClusterEvent | None], seconds: int) -> bool | None:
        if trigger.exchange_event_at is None:
            return None
        limit = trigger.exchange_event_at + timedelta(seconds=seconds)
        checked = False
        for instrument, response in responses.items():
            if instrument is trigger.instrument or response is None or response.direction in (None, PriceDirection.FLAT):
                continue
            later = [event for event in cluster.events if event.instrument is instrument and event.exchange_event_at is not None
                     and response.exchange_event_at is not None and response.exchange_event_at < event.exchange_event_at <= limit]
            if not later:
                continue
            checked = True
            if later[-1].direction is not response.direction:
                return False
        return True if checked else None

    @staticmethod
    def _alignment(reaction_class: ReactionClass, persistence: tuple[bool | None, ...]) -> AlignmentType:
        if reaction_class is ReactionClass.FULL_FOLLOW:
            if persistence[2] is True and persistence[3] is True:
                return AlignmentType.PERSISTENT_ALIGNMENT
            if persistence[0] is True:
                return AlignmentType.TRANSIENT_ALIGNMENT
            return AlignmentType.UNKNOWN
        if reaction_class is ReactionClass.PARTIAL_FOLLOW:
            return AlignmentType.PARTIAL_ALIGNMENT
        if reaction_class in (ReactionClass.NO_FOLLOW, ReactionClass.OPPOSITE_RESPONSE):
            return AlignmentType.DIVERGENCE
        return AlignmentType.UNKNOWN

    def _insufficient(self) -> ReactionAnalysis:
        return ReactionAnalysis(None, None, None, (), None, None, None, None, None, None, None, None, None,
                                ReactionClass.INSUFFICIENT_DATA, ResponseWindow(None, None, None, None, None, None),
                                None, None, None, None, AlignmentType.UNKNOWN)


def reaction_statistics(analyses: Iterable[ReactionAnalysis]) -> dict[str, object]:
    """Descriptive counts and distributions; never a score or signal."""
    rows = tuple(analyses)
    classes = Counter(row.reaction_class.value for row in rows)
    alignments = Counter(row.alignment_type.value for row in rows)
    windows: Counter[str] = Counter()
    for row in rows:
        for name, enabled in asdict(row.response_windows).items():
            if enabled is True:
                windows[name] += 1
    def distribution(values: list[float | None]) -> dict[str, float | int | None]:
        numeric = [value for value in values if value is not None]
        return {"count": len(numeric), "min": min(numeric) if numeric else None,
                "median": median(numeric) if numeric else None, "max": max(numeric) if numeric else None}
    persistence = {}
    for horizon in ("persist_1s", "persist_3s", "persist_5s", "persist_10s"):
        known = [getattr(row, horizon) for row in rows if getattr(row, horizon) is not None]
        persistence[horizon] = sum(value is True for value in known) / len(known) if known else None
    return {
        "reaction_class_count": dict(classes), "alignment_type_count": dict(alignments),
        "response_window_count": dict(windows), "persistence_rate_by_horizon": persistence,
        "reaction_latency_distribution": distribution([latency for row in rows for latency in (
            row.ir_response_latency_ms, row.tx_response_latency_ms, row.tmf_response_latency_ms)]),
        "response_change_bps_distribution": distribution([change for row in rows for change in (
            row.ir_response_change_bps, row.tx_response_change_bps, row.tmf_response_change_bps)]),
    }
