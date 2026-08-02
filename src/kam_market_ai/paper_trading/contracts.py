"""Immutable Paper Trading v0.1 contracts; no external execution boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps


PAPER_TRADING_CONTRACT_VERSION = "0.1"


class PaperTradingSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PaperTradingOrderState(StrEnum):
    REQUESTED = "requested"
    REJECTED = "rejected"
    ACCEPTED = "accepted"
    FILLED = "filled"


ORDER_STATE_TRANSITIONS = {
    PaperTradingOrderState.REQUESTED: frozenset({PaperTradingOrderState.REJECTED, PaperTradingOrderState.ACCEPTED}),
    PaperTradingOrderState.ACCEPTED: frozenset({PaperTradingOrderState.FILLED}),
    PaperTradingOrderState.REJECTED: frozenset(),
    PaperTradingOrderState.FILLED: frozenset(),
}


def _utc(value: datetime, field_name: str) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field_name} must be UTC timezone-aware.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal, field_name: str, *, positive: bool = False) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal.")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return str(value)


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperTradingOrderRequest:
    idempotency_key: str
    instrument: str
    side: PaperTradingSide
    quantity: Decimal
    price: Decimal
    created_at: datetime
    request_version: str = PAPER_TRADING_CONTRACT_VERSION
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.idempotency_key or not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("idempotency_key and canonical instrument are required.")
        _decimal(self.quantity, "quantity", positive=True)
        _decimal(self.price, "price", positive=True)
        _utc(self.created_at, "created_at")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.account_credentials_allowed is not False:
            raise ValueError("Paper Trading requests are always isolated dry runs.")

    def canonical_payload(self) -> dict[str, object]:
        return {"idempotency_key": self.idempotency_key, "instrument": self.instrument, "side": self.side.value, "quantity": _decimal(self.quantity, "quantity"), "price": _decimal(self.price, "price"), "created_at": _utc(self.created_at, "created_at"), "request_version": self.request_version, "dry_run": True, "live_order_allowed": False, "broker_connected": False, "account_credentials_allowed": False}

    @property
    def request_hash(self) -> str:
        return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class PaperTradingFill:
    fill_id: str
    idempotency_key: str
    instrument: str
    side: PaperTradingSide
    quantity: Decimal
    price: Decimal
    fees: Decimal
    filled_at: datetime

    def __post_init__(self) -> None:
        if not self.fill_id or not self.idempotency_key or not self.instrument:
            raise ValueError("Fill identity is required.")
        _decimal(self.quantity, "quantity", positive=True); _decimal(self.price, "price", positive=True); _decimal(self.fees, "fees")
        if self.fees < 0: raise ValueError("fees must be non-negative.")
        _utc(self.filled_at, "filled_at")

    def canonical_payload(self) -> dict[str, object]:
        return {"fill_id": self.fill_id, "idempotency_key": self.idempotency_key, "instrument": self.instrument, "side": self.side.value, "quantity": _decimal(self.quantity, "quantity"), "price": _decimal(self.price, "price"), "fees": _decimal(self.fees, "fees"), "filled_at": _utc(self.filled_at, "filled_at")}

    @property
    def fill_hash(self) -> str: return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class PaperTradingPosition:
    instrument: str
    quantity: Decimal
    average_price: Decimal
    realized_pnl: Decimal
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper(): raise ValueError("Position instrument must be canonical.")
        _decimal(self.quantity, "quantity"); _decimal(self.average_price, "average_price", positive=True); _decimal(self.realized_pnl, "realized_pnl"); _utc(self.updated_at, "updated_at")

    def canonical_payload(self) -> dict[str, object]:
        return {"instrument": self.instrument, "quantity": _decimal(self.quantity, "quantity"), "average_price": _decimal(self.average_price, "average_price"), "realized_pnl": _decimal(self.realized_pnl, "realized_pnl"), "updated_at": _utc(self.updated_at, "updated_at")}


@dataclass(frozen=True, slots=True)
class PaperTradingAccountSnapshot:
    positions: tuple[PaperTradingPosition, ...]
    daily_realized_pnl: Decimal
    captured_at: datetime

    def __post_init__(self) -> None:
        instruments = tuple(position.instrument for position in self.positions)
        if instruments != tuple(sorted(set(instruments))): raise ValueError("Positions must be unique and canonical ordered.")
        _decimal(self.daily_realized_pnl, "daily_realized_pnl"); _utc(self.captured_at, "captured_at")

    def canonical_payload(self) -> dict[str, object]:
        return {"positions": [position.canonical_payload() for position in self.positions], "daily_realized_pnl": _decimal(self.daily_realized_pnl, "daily_realized_pnl"), "captured_at": _utc(self.captured_at, "captured_at")}


@dataclass(frozen=True, slots=True)
class PaperTradingRiskLimits:
    max_order_quantity: Decimal
    max_notional: Decimal
    max_daily_loss: Decimal
    max_open_positions: int
    allowed_instruments: tuple[str, ...]
    allowed_weekdays: tuple[int, ...]
    session_start: time
    session_end: time

    def __post_init__(self) -> None:
        _decimal(self.max_order_quantity, "max_order_quantity", positive=True); _decimal(self.max_notional, "max_notional", positive=True); _decimal(self.max_daily_loss, "max_daily_loss", positive=True)
        if not isinstance(self.max_open_positions, int) or self.max_open_positions < 0: raise ValueError("max_open_positions must be non-negative.")
        if self.allowed_instruments != tuple(sorted(set(self.allowed_instruments))) or not self.allowed_instruments: raise ValueError("allowed_instruments must be non-empty canonical ordered.")
        if self.allowed_weekdays != tuple(sorted(set(self.allowed_weekdays))) or any(day < 0 or day > 6 for day in self.allowed_weekdays): raise ValueError("allowed_weekdays must be canonical weekdays.")
        if self.session_start >= self.session_end: raise ValueError("Session must not cross midnight.")


@dataclass(frozen=True, slots=True)
class PaperTradingSafetyState:
    paper_trading_enabled: bool = False
    emergency_stop: bool = True
    used_idempotency_keys: tuple[str, ...] = ()
    account_snapshot: PaperTradingAccountSnapshot | None = None
    risk_limits: PaperTradingRiskLimits | None = None
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if self.used_idempotency_keys != tuple(sorted(set(self.used_idempotency_keys))) or any(not item for item in self.used_idempotency_keys): raise ValueError("Idempotency keys must be unique and canonical ordered.")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.account_credentials_allowed is not False: raise ValueError("Paper Trading safety state is always isolated.")


@dataclass(frozen=True, slots=True)
class PaperTradingOrderResult:
    idempotency_key: str
    state: PaperTradingOrderState
    reason_codes: tuple[str, ...]
    request_hash: str
    evaluated_at: datetime
    result_version: str = PAPER_TRADING_CONTRACT_VERSION
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if self.state not in {PaperTradingOrderState.REJECTED, PaperTradingOrderState.ACCEPTED}: raise ValueError("Safety results may only accept or reject a request.")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))) or any(not item for item in self.reason_codes): raise ValueError("Result reason codes must be canonical.")
        if self.state is PaperTradingOrderState.ACCEPTED and self.reason_codes: raise ValueError("Accepted result cannot contain rejection reasons.")
        if self.state is PaperTradingOrderState.REJECTED and not self.reason_codes: raise ValueError("Rejected result requires a reason.")
        _utc(self.evaluated_at, "evaluated_at")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.account_credentials_allowed is not False: raise ValueError("Paper Trading result is always isolated.")

    def canonical_payload(self) -> dict[str, object]:
        return {"idempotency_key": self.idempotency_key, "state": self.state.value, "reason_codes": list(self.reason_codes), "request_hash": self.request_hash, "evaluated_at": _utc(self.evaluated_at, "evaluated_at"), "result_version": self.result_version, "dry_run": True, "live_order_allowed": False, "broker_connected": False, "account_credentials_allowed": False}

    @property
    def result_hash(self) -> str: return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class PaperTradingAuditEvent:
    event_type: str
    request_hash: str
    result_hash: str
    occurred_at: datetime
    reason_codes: tuple[str, ...]
    event_version: str = PAPER_TRADING_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.event_type not in {"order_rejected", "order_accepted"}: raise ValueError("Unknown audit event type.")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))): raise ValueError("Audit reason codes must be canonical.")
        _utc(self.occurred_at, "occurred_at")

    def canonical_payload(self) -> dict[str, object]:
        return {"event_type": self.event_type, "request_hash": self.request_hash, "result_hash": self.result_hash, "occurred_at": _utc(self.occurred_at, "occurred_at"), "reason_codes": list(self.reason_codes), "event_version": self.event_version}

    @property
    def event_hash(self) -> str: return _hash(self.canonical_payload())
