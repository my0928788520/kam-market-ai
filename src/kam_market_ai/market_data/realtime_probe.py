"""Bounded, read-only cross-market WebSocket observation probe.

This module contains no SDK construction, credential, account, order, or
trading surface.  It accepts only AuthorizedMarketDataClients.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Any

from ..analysis.reaction_chain import ClusterEvent, EventCluster, ReactionChainEngine, reaction_statistics
from ..models import Instrument, Tick
from ..storage import ShadowStore
from .fubon_neo import AuthorizedMarketDataClients, FubonNeoMarketDataAdapter


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    instrument: Instrument
    source_symbol: str
    source_channel: str
    exchange_event_at: datetime
    kam_received_at: datetime
    price: float
    size_or_volume: int
    after_hours: bool
    baseline_price: float | None

    def payload(self) -> dict[str, object]:
        data = asdict(self)
        data["instrument"] = self.instrument.value
        data["exchange_event_at"] = self.exchange_event_at.isoformat()
        data["kam_received_at"] = self.kam_received_at.isoformat()
        return data


@dataclass(frozen=True, slots=True)
class ActiveContracts:
    tx_symbol: str
    tmf_symbol: str


@dataclass(frozen=True, slots=True)
class ProbeReport:
    active_tx_symbol: str | None
    active_tmf_symbol: str | None
    event_count_by_instrument: dict[str, int]
    exchange_timestamp_missing_count: int
    mapper_failure_count: int
    event_cluster_count: int
    reaction_analysis_count: int
    reaction_storage_count: int
    first_event_count_by_instrument: dict[str, int]
    event_order_count: int
    reaction_class_count: dict[str, int]
    alignment_type_count: dict[str, int]
    unsubscribe_success: bool
    disconnect_success: bool
    receive_order_differs_from_exchange_order: bool
    callback_or_timestamp_issue: bool
    reconnect_issue: bool


class ActiveContractProbe:
    """Discovers current contracts using ticker metadata plus quote volume."""

    _families = {
        Instrument.TX: "臺股期貨",
        Instrument.MTX: "微型臺指期貨",
    }

    def __init__(self, clients: AuthorizedMarketDataClients) -> None:
        self._rest = clients.futopt_rest.intraday

    def resolve(self, *, after_hours: bool = False, today: date | None = None) -> ActiveContracts:
        payload = self._rest.tickers(type="FUTURE", exchange="TAIFEX")
        rows = payload.get("data", []) if isinstance(payload, Mapping) else []
        if not isinstance(rows, list):
            raise RuntimeError("Ticker discovery returned no list")
        today = today or datetime.now(UTC).date()
        selected: dict[Instrument, str] = {}
        for instrument, name_prefix in self._families.items():
            candidates: list[tuple[int, str]] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                symbol, name, end_date = row.get("symbol"), row.get("name"), row.get("endDate")
                if not isinstance(symbol, str) or not isinstance(name, str) or not name.startswith(name_prefix):
                    continue
                try:
                    if not isinstance(end_date, str) or date.fromisoformat(end_date) < today:
                        continue
                except ValueError:
                    continue
                params: dict[str, object] = {"symbol": symbol}
                if after_hours:
                    params["session"] = "afterhours"
                quote = self._rest.quote(**params)
                total = quote.get("total", {}) if isinstance(quote, Mapping) else {}
                volume = total.get("tradeVolume") if isinstance(total, Mapping) else None
                if isinstance(volume, (int, float)):
                    candidates.append((int(volume), symbol))
            if not candidates:
                raise RuntimeError(f"No active {instrument.value} candidate with comparable trade volume")
            # Activity (trade volume) is primary. A symbol tie is not resolved by
            # month; it is an explicit ambiguity, not a hidden contract choice.
            best_volume = max(volume for volume, _ in candidates)
            best = [symbol for volume, symbol in candidates if volume == best_volume]
            if len(best) != 1:
                raise RuntimeError(f"Ambiguous active {instrument.value} candidate")
            selected[instrument] = best[0]
        return ActiveContracts(selected[Instrument.TX], selected[Instrument.MTX])


class BoundedReactionObserver:
    """Connects, observes a bounded interval, then always unsubscribes/disconnects."""

    def __init__(self, clients: AuthorizedMarketDataClients, storage_path: str | Path) -> None:
        self._clients = clients
        self._store = ShadowStore(storage_path)

    def observe(self, contracts: ActiveContracts, *, duration_seconds: float = 120.0,
                after_hours: bool = False) -> ProbeReport:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        self._store.initialize()
        events: list[ObservedEvent] = []
        lock = threading.Lock()
        counters: Counter[str] = Counter()
        last_price: dict[Instrument, float] = {}
        symbols = {contracts.tx_symbol: Instrument.TX, contracts.tmf_symbol: Instrument.MTX}
        futures_params = [self._futures_params(symbol, after_hours) for symbol in symbols]
        stock_params = {"channel": "indices", "symbol": "IR0001"}
        cleanup = {"unsubscribe": True, "disconnect": True, "callback": True}
        connections = {"futopt": False, "stock": False}

        def append(tick: Tick, received: datetime) -> None:
            if tick.timestamp is None:
                counters["timestamp_missing"] += 1
                return
            with lock:
                baseline = last_price.get(tick.instrument)
                last_price[tick.instrument] = tick.price
                events.append(ObservedEvent(
                    tick.instrument, tick.source_symbol or "", tick.source_channel or "", tick.timestamp,
                    received, tick.price, tick.volume, bool(tick.after_hours), baseline,
                ))

        def futures_handler(message: str | Mapping[str, Any]) -> None:
            received = datetime.now(UTC)
            try:
                decoded = FubonNeoMarketDataAdapter._decode_futures_trades(message, symbols, after_hours)
                if self._is_expected_data(message, "trades") and not decoded:
                    counters["mapper_failure"] += 1
                    if self._missing_time(message):
                        counters["timestamp_missing"] += 1
                for tick in decoded:
                    append(tick, received)
            except Exception:
                counters["mapper_failure"] += 1

        def stock_handler(message: str | Mapping[str, Any]) -> None:
            received = datetime.now(UTC)
            try:
                tick = FubonNeoMarketDataAdapter._decode_taiex_index(message)
                if self._is_expected_data(message, "indices") and tick is None:
                    counters["mapper_failure"] += 1
                    if self._missing_time(message):
                        counters["timestamp_missing"] += 1
                if tick is not None:
                    append(tick, received)
            except Exception:
                counters["mapper_failure"] += 1

        self._clients.futopt_websocket.on("message", futures_handler)
        self._clients.stock_websocket.on("message", stock_handler)
        try:
            self._clients.futopt_websocket.connect(); connections["futopt"] = True
            for params in futures_params:
                self._clients.futopt_websocket.subscribe(params)
            self._clients.stock_websocket.connect(); connections["stock"] = True
            self._clients.stock_websocket.subscribe(stock_params)
            deadline = monotonic() + duration_seconds
            while monotonic() < deadline:
                threading.Event().wait(min(0.25, deadline - monotonic()))
        finally:
            for params in futures_params:
                try:
                    self._clients.futopt_websocket.unsubscribe(params)
                except Exception:
                    cleanup["unsubscribe"] = False
            try:
                self._clients.stock_websocket.unsubscribe(stock_params)
            except Exception:
                cleanup["unsubscribe"] = False
            for name, websocket in (("futopt", self._clients.futopt_websocket), ("stock", self._clients.stock_websocket)):
                if connections[name]:
                    try:
                        websocket.disconnect()
                    except Exception:
                        cleanup["disconnect"] = False
            for websocket, handler in ((self._clients.futopt_websocket, futures_handler),
                                       (self._clients.stock_websocket, stock_handler)):
                try:
                    websocket.off("message", handler)
                except Exception:
                    cleanup["callback"] = False

        return self._analyze_and_store(events, counters, contracts, cleanup)

    @staticmethod
    def _futures_params(symbol: str, after_hours: bool) -> dict[str, object]:
        params: dict[str, object] = {"channel": "trades", "symbol": symbol}
        if after_hours:
            params["afterHours"] = True
        return params

    @staticmethod
    def _message_data(message: str | Mapping[str, Any]) -> Mapping[str, Any] | None:
        try:
            event = json.loads(message) if isinstance(message, str) else message
        except (TypeError, ValueError):
            return None
        return event if isinstance(event, Mapping) else None

    @classmethod
    def _is_expected_data(cls, message: str | Mapping[str, Any], channel: str) -> bool:
        event = cls._message_data(message)
        return bool(event and event.get("event") == "data" and event.get("channel") == channel)

    @classmethod
    def _missing_time(cls, message: str | Mapping[str, Any]) -> bool:
        event = cls._message_data(message)
        data = event.get("data") if event else None
        return isinstance(data, Mapping) and "time" not in data

    def _analyze_and_store(self, events: list[ObservedEvent], counters: Counter[str], contracts: ActiveContracts,
                           cleanup: dict[str, bool]) -> ProbeReport:
        for item in events:
            self._store.append_observation(item.kam_received_at.isoformat(), "REACTION_EVENT_V0_1", item.payload())
        clusters = self._clusters(events)
        engine = ReactionChainEngine()
        analyses = [engine.analyze(cluster) for cluster in clusters]
        for analysis in analyses:
            observed_at = analysis.trigger_event_at.isoformat() if analysis.trigger_event_at else datetime.now(UTC).isoformat()
            self._store.save_reaction_analysis(analysis, observed_at)
        stats = reaction_statistics(analyses)
        first = Counter(analysis.trigger_instrument.value for analysis in analyses if analysis.trigger_instrument)
        counts = Counter(event.instrument.value for event in events)
        received_order_differs = any(
            [item.instrument for item in raw] != [item.instrument for item in ordered.events]
            for raw, ordered in ((raw, EventCluster.from_events(
                ClusterEvent(item.instrument, item.price, item.baseline_price, item.exchange_event_at, item.kam_received_at)
                for item in raw)) for raw in self._raw_cluster_groups(events))
        )
        return ProbeReport(
            contracts.tx_symbol, contracts.tmf_symbol, dict(counts), counters["timestamp_missing"],
            counters["mapper_failure"], len(clusters), len(analyses), len(analyses), dict(first),
            sum(len(analysis.response_order) for analysis in analyses),
            stats["reaction_class_count"], stats["alignment_type_count"], cleanup["unsubscribe"], cleanup["disconnect"],
            received_order_differs, bool(counters["mapper_failure"] or counters["timestamp_missing"] or not cleanup["callback"]), False,
        )

    def _raw_cluster_groups(self, events: list[ObservedEvent]) -> list[list[ObservedEvent]]:
        ordered = sorted(events, key=lambda event: event.exchange_event_at)
        groups: list[list[ObservedEvent]] = []
        for event in ordered:
            if not groups or event.exchange_event_at - groups[-1][0].exchange_event_at > timedelta(milliseconds=500):
                groups.append([event])
            else:
                groups[-1].append(event)
        return groups

    def _clusters(self, events: list[ObservedEvent]) -> list[EventCluster]:
        return [EventCluster.from_events(
            ClusterEvent(item.instrument, item.price, item.baseline_price, item.exchange_event_at, item.kam_received_at)
            for item in group
        ) for group in self._raw_cluster_groups(events)]
