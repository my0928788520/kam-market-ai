"""Bounded, market-data-only verification for live Fubon futures quotes.

The probe accepts only the already-authorized market-data clients.  It never
receives an SDK, account, order, balance, or position object and never stores a
raw provider payload.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

from .fubon_neo import AuthorizedMarketDataClients


class FuturesProductCode(StrEnum):
    TX = "TX"
    MTX = "MTX"
    TMF = "TMF"


class FuturesLiveProbeFailure(StrEnum):
    NONE = "NONE"
    CONTRACT_DISCOVERY_ERROR = "CONTRACT_DISCOVERY_ERROR"
    CONNECT_ERROR = "CONNECT_ERROR"
    CONNECT_TIMEOUT = "CONNECT_TIMEOUT"
    AUTH_TIMEOUT = "AUTH_TIMEOUT"
    SUBSCRIBE_ERROR = "SUBSCRIBE_ERROR"
    SUBSCRIBE_ACK_TIMEOUT = "SUBSCRIBE_ACK_TIMEOUT"
    NO_FRESH_DATA = "NO_FRESH_DATA"
    PROVIDER_PAYLOAD_ERROR = "PROVIDER_PAYLOAD_ERROR"
    UNEXPECTED_DISCONNECT = "UNEXPECTED_DISCONNECT"
    UNSUBSCRIBE_ERROR = "UNSUBSCRIBE_ERROR"
    DISCONNECT_ERROR = "DISCONNECT_ERROR"


class FuturesContractDiscoveryError(RuntimeError):
    """Stable discovery failure without provider response or credential data."""


_PRODUCT_PREFIXES = {
    FuturesProductCode.TX: "TXF",
    FuturesProductCode.MTX: "MXF",
    FuturesProductCode.TMF: "TMF",
}

_PRODUCT_NAMES = {
    FuturesProductCode.TX: "臺股期貨",
    FuturesProductCode.MTX: "小型臺指期貨",
    FuturesProductCode.TMF: "微型臺指期貨",
}


@dataclass(frozen=True, slots=True)
class FubonLiveFuturesContract:
    product_code: FuturesProductCode
    provider_symbol: str
    contract_code: str
    contract_month: str
    end_date: date
    observed_volume: int
    after_hours: bool

    def safe_payload(self) -> dict[str, object]:
        return {
            "product_code": self.product_code.value,
            "provider_symbol": self.provider_symbol,
            "contract_code": self.contract_code,
            "contract_month": self.contract_month,
            "end_date": self.end_date.isoformat(),
            "observed_volume": self.observed_volume,
            "after_hours": self.after_hours,
        }


class FubonFuturesContractDiscovery:
    """Resolve TX, MTX, and TMF by verified identity plus highest quote volume."""

    def __init__(self, clients: AuthorizedMarketDataClients) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        self._intraday = clients.futopt_rest.intraday

    def resolve(
        self,
        *,
        after_hours: bool = False,
        today: date | None = None,
    ) -> tuple[FubonLiveFuturesContract, ...]:
        session = "AFTERHOURS" if after_hours else "REGULAR"
        try:
            payload = self._intraday.tickers(
                type="FUTURE",
                exchange="TAIFEX",
                session=session,
                contractType="I",
            )
        except Exception:
            raise FuturesContractDiscoveryError("TICKERS_UNAVAILABLE") from None
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            raise FuturesContractDiscoveryError("TICKERS_MALFORMED")
        local_today = today or datetime.now(ZoneInfo("Asia/Taipei")).date()
        return tuple(
            self._resolve_product(product, rows, after_hours, local_today)
            for product in FuturesProductCode
        )

    def _resolve_product(
        self,
        product: FuturesProductCode,
        rows: list[object],
        after_hours: bool,
        today: date,
    ) -> FubonLiveFuturesContract:
        candidates: list[FubonLiveFuturesContract] = []
        for row in rows:
            identity = self._validated_identity(product, row, today)
            if identity is None:
                continue
            symbol, end_date = identity
            params: dict[str, object] = {"symbol": symbol}
            if after_hours:
                params["session"] = "afterhours"
            try:
                quote = self._intraday.quote(**params)
            except Exception:
                raise FuturesContractDiscoveryError("QUOTE_UNAVAILABLE") from None
            total = quote.get("total") if isinstance(quote, Mapping) else None
            volume = total.get("tradeVolume") if isinstance(total, Mapping) else None
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or volume < 0:
                continue
            month = end_date.strftime("%Y%m")
            prefix = _PRODUCT_PREFIXES[product]
            candidates.append(
                FubonLiveFuturesContract(
                    product,
                    symbol,
                    f"{prefix}{month}",
                    month,
                    end_date,
                    int(volume),
                    after_hours,
                )
            )
        if not candidates:
            raise FuturesContractDiscoveryError(f"NO_{product.value}_CONTRACT")
        best_volume = max(item.observed_volume for item in candidates)
        best = tuple(item for item in candidates if item.observed_volume == best_volume)
        if len(best) != 1:
            raise FuturesContractDiscoveryError(f"AMBIGUOUS_{product.value}_CONTRACT")
        return best[0]

    @staticmethod
    def _validated_identity(
        product: FuturesProductCode,
        row: object,
        today: date,
    ) -> tuple[str, date] | None:
        if not isinstance(row, Mapping):
            return None
        symbol, name, raw_end_date = row.get("symbol"), row.get("name"), row.get("endDate")
        if (
            not isinstance(symbol, str)
            or not isinstance(name, str)
            or not isinstance(raw_end_date, str)
        ):
            return None
        prefix = _PRODUCT_PREFIXES[product]
        if re.fullmatch(rf"{prefix}[A-L]\d", symbol) is None or not name.startswith(
            _PRODUCT_NAMES[product]
        ):
            return None
        try:
            end_date = date.fromisoformat(raw_end_date)
        except ValueError:
            return None
        expected_month_letter = chr(ord("A") + end_date.month - 1)
        if (
            end_date < today
            or symbol[-2] != expected_month_letter
            or symbol[-1] != str(end_date.year)[-1]
        ):
            return None
        return symbol, end_date


def _decoded_message(value: str | Mapping[str, Any]) -> Mapping[str, Any] | None:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _provider_timestamp(value: object) -> datetime:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("invalid provider timestamp")
    numeric = float(value)
    if numeric > 100_000_000_000_000:
        numeric /= 1_000_000
    elif numeric > 100_000_000_000:
        numeric /= 1_000
    return datetime.fromtimestamp(numeric, tz=UTC)


@dataclass(slots=True)
class _CycleState:
    expected_symbols: frozenset[str]
    clock: Callable[[], datetime]
    stale_after_seconds: float
    connected: bool = False
    authenticated: bool = False
    disconnected: bool = False
    provider_error: bool = False
    malformed_count: int = 0
    unexpected_symbol_count: int = 0
    subscription_ids: dict[str, str] = field(default_factory=dict)
    unsubscribed_ids: set[str] = field(default_factory=set)
    event_counts: dict[str, int] = field(default_factory=dict)
    latest_age_seconds: dict[str, float] = field(default_factory=dict)
    stale_symbols: set[str] = field(default_factory=set)
    changed: threading.Event = field(default_factory=threading.Event, repr=False)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def notify(self) -> None:
        self.changed.set()

    def on_message(self, value: str | Mapping[str, Any]) -> None:
        message = _decoded_message(value)
        if message is None:
            with self.lock:
                self.malformed_count += 1
            self.notify()
            return
        event = message.get("event")
        if event == "authenticated":
            self.authenticated = True
        elif event == "subscribed":
            self._record_subscription(message.get("data"))
        elif event == "unsubscribed":
            self._record_unsubscription(message.get("data"))
        elif event == "data" and message.get("channel") == "trades":
            self._record_trade(message.get("data"))
        self.notify()

    def _record_subscription(self, value: object) -> None:
        items = value if isinstance(value, list) else [value]
        with self.lock:
            for item in items:
                if not isinstance(item, Mapping):
                    self.malformed_count += 1
                    continue
                symbol, channel_id = item.get("symbol"), item.get("id")
                if symbol in self.expected_symbols and isinstance(channel_id, str) and channel_id:
                    self.subscription_ids[str(symbol)] = channel_id
                else:
                    self.malformed_count += 1

    def _record_unsubscription(self, value: object) -> None:
        items = value if isinstance(value, list) else [value]
        with self.lock:
            for item in items:
                channel_id = item.get("id") if isinstance(item, Mapping) else None
                if isinstance(channel_id, str):
                    self.unsubscribed_ids.add(channel_id)

    def _record_trade(self, value: object) -> None:
        if not isinstance(value, Mapping):
            with self.lock:
                self.malformed_count += 1
            return
        symbol, trades, timestamp = value.get("symbol"), value.get("trades"), value.get("time")
        if symbol not in self.expected_symbols:
            with self.lock:
                self.unexpected_symbol_count += 1
            return
        if not isinstance(trades, list) or not trades:
            with self.lock:
                self.malformed_count += 1
            return
        prices_valid = all(
            isinstance(item, Mapping)
            and isinstance(item.get("price"), (int, float))
            and not isinstance(item.get("price"), bool)
            for item in trades
        )
        try:
            source_at = _provider_timestamp(timestamp)
        except (OverflowError, OSError, ValueError):
            source_at = None
        if not prices_valid or source_at is None:
            with self.lock:
                self.malformed_count += 1
            return
        age = (self.clock() - source_at).total_seconds()
        with self.lock:
            if age < -5:
                self.malformed_count += 1
                return
            normalized_age = max(0.0, age)
            self.event_counts[str(symbol)] = self.event_counts.get(str(symbol), 0) + 1
            self.latest_age_seconds[str(symbol)] = normalized_age
            if normalized_age > self.stale_after_seconds:
                self.stale_symbols.add(str(symbol))
            else:
                self.stale_symbols.discard(str(symbol))


@dataclass(frozen=True, slots=True)
class FubonFuturesProbeCycle:
    phase: str
    connected: bool
    authenticated: bool
    subscribed_symbols: tuple[str, ...]
    data_event_count: tuple[tuple[str, int], ...]
    latest_age_seconds: tuple[tuple[str, float], ...]
    unsubscribe_success: bool
    disconnect_success: bool
    failure_stage: FuturesLiveProbeFailure

    @property
    def success(self) -> bool:
        return self.failure_stage is FuturesLiveProbeFailure.NONE

    def safe_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "connected": self.connected,
            "authenticated": self.authenticated,
            "subscribed_symbols": list(self.subscribed_symbols),
            "data_event_count": dict(self.data_event_count),
            "latest_age_seconds": dict(self.latest_age_seconds),
            "unsubscribe_success": self.unsubscribe_success,
            "disconnect_success": self.disconnect_success,
            "failure_stage": self.failure_stage.value,
        }


@dataclass(frozen=True, slots=True)
class FubonFuturesLiveProbeReport:
    contracts: tuple[FubonLiveFuturesContract, ...]
    cycles: tuple[FubonFuturesProbeCycle, ...]
    failure_stage: FuturesLiveProbeFailure
    market_data_only: bool = True
    account_connected: bool = False
    broker_connected: bool = False
    trading_enabled: bool = False
    live_order_allowed: bool = False

    @property
    def success(self) -> bool:
        return self.failure_stage is FuturesLiveProbeFailure.NONE and all(
            cycle.success for cycle in self.cycles
        )

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": self.success,
            "failure_stage": self.failure_stage.value,
            "contracts": [item.safe_payload() for item in self.contracts],
            "cycles": [item.safe_payload() for item in self.cycles],
            "market_data_only": self.market_data_only,
            "account_connected": self.account_connected,
            "broker_connected": self.broker_connected,
            "trading_enabled": self.trading_enabled,
            "live_order_allowed": self.live_order_allowed,
        }


class FubonFuturesLiveProbe:
    """Run one bounded quote cycle and, optionally, a controlled reconnect cycle."""

    def __init__(
        self,
        clients: AuthorizedMarketDataClients,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        connect_timeout_seconds: float = 10.0,
        subscribe_timeout_seconds: float = 10.0,
        stale_after_seconds: float = 300.0,
        cleanup_timeout_seconds: float = 5.0,
    ) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        if min(
            connect_timeout_seconds,
            subscribe_timeout_seconds,
            stale_after_seconds,
            cleanup_timeout_seconds,
        ) <= 0:
            raise ValueError("probe timeouts must be positive")
        self._websocket = clients.futopt_websocket
        self._clock = clock
        self._connect_timeout = connect_timeout_seconds
        self._subscribe_timeout = subscribe_timeout_seconds
        self._stale_after = stale_after_seconds
        self._cleanup_timeout = cleanup_timeout_seconds

    def run(
        self,
        contracts: tuple[FubonLiveFuturesContract, ...],
        *,
        duration_seconds: float = 30.0,
        verify_reconnect: bool = False,
    ) -> FubonFuturesLiveProbeReport:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if tuple(item.product_code for item in contracts) != tuple(FuturesProductCode):
            raise ValueError("TX, MTX, and TMF contracts are required in canonical order")
        initial = self._run_cycle("initial", contracts, duration_seconds)
        cycles = [initial]
        failure = initial.failure_stage
        if initial.success and verify_reconnect:
            reconnect = self._run_cycle("controlled-reconnect", contracts, duration_seconds)
            cycles.append(reconnect)
            failure = reconnect.failure_stage
        return FubonFuturesLiveProbeReport(contracts, tuple(cycles), failure)

    def _run_cycle(
        self,
        phase: str,
        contracts: tuple[FubonLiveFuturesContract, ...],
        duration_seconds: float,
    ) -> FubonFuturesProbeCycle:
        symbols = frozenset(item.provider_symbol for item in contracts)
        after_hours = contracts[0].after_hours
        state = _CycleState(symbols, self._clock, self._stale_after)
        listeners = self._listeners(state)
        failure = FuturesLiveProbeFailure.NONE
        unsubscribe_success = False
        disconnect_success = False
        connect_called = False
        try:
            for event, listener in listeners:
                self._websocket.on(event, listener)
            try:
                connect_called = True
                self._websocket.connect()
            except Exception:
                failure = FuturesLiveProbeFailure.CONNECT_ERROR
            if failure is FuturesLiveProbeFailure.NONE and not self._wait(
                state, lambda: state.connected or state.provider_error, self._connect_timeout
            ):
                failure = FuturesLiveProbeFailure.CONNECT_TIMEOUT
            if failure is FuturesLiveProbeFailure.NONE and state.provider_error:
                failure = FuturesLiveProbeFailure.CONNECT_ERROR
            if failure is FuturesLiveProbeFailure.NONE and not self._wait(
                state, lambda: state.authenticated or state.provider_error, self._connect_timeout
            ):
                failure = FuturesLiveProbeFailure.AUTH_TIMEOUT
            if failure is FuturesLiveProbeFailure.NONE and state.provider_error:
                failure = FuturesLiveProbeFailure.AUTH_TIMEOUT
            if failure is FuturesLiveProbeFailure.NONE:
                for contract in contracts:
                    params: dict[str, object] = {
                        "channel": "trades",
                        "symbol": contract.provider_symbol,
                    }
                    if after_hours:
                        params["afterHours"] = True
                    try:
                        self._websocket.subscribe(params)
                    except Exception:
                        failure = FuturesLiveProbeFailure.SUBSCRIBE_ERROR
                        break
            if failure is FuturesLiveProbeFailure.NONE and not self._wait(
                state,
                lambda: set(state.subscription_ids) == set(symbols)
                or state.provider_error
                or state.disconnected,
                self._subscribe_timeout,
            ):
                failure = FuturesLiveProbeFailure.SUBSCRIBE_ACK_TIMEOUT
            if failure is FuturesLiveProbeFailure.NONE and state.provider_error:
                failure = FuturesLiveProbeFailure.SUBSCRIBE_ERROR
            if failure is FuturesLiveProbeFailure.NONE and state.disconnected:
                failure = FuturesLiveProbeFailure.UNEXPECTED_DISCONNECT
            if failure is FuturesLiveProbeFailure.NONE and not self._wait(
                state,
                lambda: set(state.event_counts) == set(symbols)
                or state.provider_error
                or state.disconnected
                or state.malformed_count > 0
                or state.unexpected_symbol_count > 0,
                duration_seconds,
            ):
                failure = FuturesLiveProbeFailure.NO_FRESH_DATA
            if failure is FuturesLiveProbeFailure.NONE and state.disconnected:
                failure = FuturesLiveProbeFailure.UNEXPECTED_DISCONNECT
            if failure is FuturesLiveProbeFailure.NONE and (
                state.provider_error
                or state.malformed_count
                or state.unexpected_symbol_count
                or state.stale_symbols
            ):
                failure = FuturesLiveProbeFailure.PROVIDER_PAYLOAD_ERROR
        except Exception:
            if failure is FuturesLiveProbeFailure.NONE:
                failure = FuturesLiveProbeFailure.CONNECT_ERROR
        finally:
            unsubscribe_success = self._unsubscribe(state)
            disconnect_success = self._disconnect(state, connect_called)
            for event, listener in listeners:
                try:
                    self._websocket.off(event, listener)
                except Exception:
                    pass
        if failure is FuturesLiveProbeFailure.NONE and not unsubscribe_success:
            failure = FuturesLiveProbeFailure.UNSUBSCRIBE_ERROR
        if failure is FuturesLiveProbeFailure.NONE and not disconnect_success:
            failure = FuturesLiveProbeFailure.DISCONNECT_ERROR
        return FubonFuturesProbeCycle(
            phase,
            state.connected,
            state.authenticated,
            tuple(sorted(state.subscription_ids)),
            tuple(sorted(state.event_counts.items())),
            tuple(
                sorted((key, round(value, 3)) for key, value in state.latest_age_seconds.items())
            ),
            unsubscribe_success,
            disconnect_success,
            failure,
        )

    @staticmethod
    def _listeners(state: _CycleState) -> tuple[tuple[str, Callable[..., None]], ...]:
        def connected(*_: object) -> None:
            state.connected = True
            state.notify()

        def authenticated(*_: object) -> None:
            state.authenticated = True
            state.notify()

        def provider_error(*_: object) -> None:
            state.provider_error = True
            state.notify()

        def disconnected(*_: object) -> None:
            state.disconnected = True
            state.notify()

        def message(value: str | Mapping[str, Any]) -> None:
            state.on_message(value)

        return (
            ("connect", connected),
            ("authenticated", authenticated),
            ("error", provider_error),
            ("disconnect", disconnected),
            ("message", message),
        )

    @staticmethod
    def _wait(state: _CycleState, predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = monotonic() + timeout
        while not predicate():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            state.changed.wait(min(0.1, remaining))
            state.changed.clear()
        return True

    def _unsubscribe(self, state: _CycleState) -> bool:
        channel_ids = tuple(sorted(state.subscription_ids.values()))
        if not channel_ids:
            return False
        params: dict[str, object] = (
            {"id": channel_ids[0]} if len(channel_ids) == 1 else {"ids": list(channel_ids)}
        )
        try:
            self._websocket.unsubscribe(params)
        except Exception:
            return False
        return self._wait(
            state,
            lambda: state.unsubscribed_ids.issuperset(channel_ids),
            self._cleanup_timeout,
        )

    def _disconnect(self, state: _CycleState, connect_called: bool) -> bool:
        if not connect_called:
            return False
        try:
            self._websocket.disconnect()
        except Exception:
            return False
        return self._wait(state, lambda: state.disconnected, self._cleanup_timeout)


__all__ = [
    "FubonFuturesContractDiscovery",
    "FubonFuturesLiveProbe",
    "FubonFuturesLiveProbeReport",
    "FubonFuturesProbeCycle",
    "FubonLiveFuturesContract",
    "FuturesContractDiscoveryError",
    "FuturesLiveProbeFailure",
    "FuturesProductCode",
]
