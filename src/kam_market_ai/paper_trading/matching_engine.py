"""Deterministic in-memory matching over explicit offline market snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps

from .contracts import PaperTradingOrderRequest, PaperTradingSafetyState, PaperTradingSide
from .ledger import PaperTradingLedger, PaperTradingLedgerTransaction, apply_paper_fill, reserve_idempotency_key
from .safety import evaluate_paper_trading_order
from .contracts import PaperTradingFill


PAPER_TRADING_MATCHING_ENGINE_VERSION = "0.1"


class PaperTradingOrderType(StrEnum): MARKET = "market"; LIMIT = "limit"
class PaperTradingMatchState(StrEnum): REJECTED = "rejected"; OPEN = "open"; PARTIALLY_FILLED = "partially_filled"; FILLED = "filled"; CANCELLED = "cancelled"


def _decimal(value: Decimal, field_name: str, *, positive: bool = False) -> str:
    if not isinstance(value, Decimal) or not value.is_finite(): raise ValueError(f"{field_name} must be finite Decimal.")
    if positive and value <= 0: raise ValueError(f"{field_name} must be positive.")
    return str(value)
def _utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value): raise ValueError("Snapshot timestamp must be UTC timezone-aware.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
def _hash(payload: object) -> str: return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OfflineMarketSnapshot:
    instrument: str
    bid_price: Decimal
    ask_price: Decimal
    available_bid_quantity: Decimal
    available_ask_quantity: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper(): raise ValueError("Snapshot instrument must be canonical.")
        for name, value in (("bid_price", self.bid_price), ("ask_price", self.ask_price), ("available_bid_quantity", self.available_bid_quantity), ("available_ask_quantity", self.available_ask_quantity)): _decimal(value, name, positive=True)
        if self.bid_price > self.ask_price: raise ValueError("Snapshot bid cannot exceed ask.")
        _utc(self.observed_at)
    def canonical_payload(self) -> dict[str, str]: return {"instrument": self.instrument, "bid_price": _decimal(self.bid_price, "bid_price"), "ask_price": _decimal(self.ask_price, "ask_price"), "available_bid_quantity": _decimal(self.available_bid_quantity, "available_bid_quantity"), "available_ask_quantity": _decimal(self.available_ask_quantity, "available_ask_quantity"), "observed_at": _utc(self.observed_at)}
    @property
    def snapshot_hash(self) -> str: return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class InMemoryPaperOrderBook:
    snapshots: tuple[OfflineMarketSnapshot, ...]
    def __post_init__(self) -> None:
        instruments = tuple(item.instrument for item in self.snapshots)
        if instruments != tuple(sorted(set(instruments))): raise ValueError("Snapshots must be unique and canonical ordered.")
    def snapshot_for(self, instrument: str) -> OfflineMarketSnapshot | None:
        return next((item for item in self.snapshots if item.instrument == instrument), None)


@dataclass(frozen=True, slots=True)
class PaperTradingMatchingAudit:
    event_type: str
    request_hash: str
    snapshot_hash: str | None
    fill_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    occurred_at: datetime
    def __post_init__(self) -> None:
        if self.event_type not in {"order_rejected", "order_open", "order_partially_filled", "order_filled", "order_cancelled"}: raise ValueError("Unknown matching audit event.")
        if self.fill_hashes != tuple(sorted(self.fill_hashes)) or self.reason_codes != tuple(sorted(set(self.reason_codes))): raise ValueError("Audit values must be canonical.")
        _utc(self.occurred_at)
    def canonical_payload(self) -> dict[str, object]: return {"event_type": self.event_type, "request_hash": self.request_hash, "snapshot_hash": self.snapshot_hash, "fill_hashes": list(self.fill_hashes), "reason_codes": list(self.reason_codes), "occurred_at": _utc(self.occurred_at)}
    @property
    def audit_hash(self) -> str: return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class PaperTradingMatchingResult:
    state: PaperTradingMatchState
    request_hash: str
    fills: tuple[PaperTradingFill, ...]
    ledger: PaperTradingLedger
    transaction: PaperTradingLedgerTransaction | None
    reason_codes: tuple[str, ...]
    audit_event: PaperTradingMatchingAudit
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False
    def __post_init__(self) -> None:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))): raise ValueError("Matching reason codes must be canonical.")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.account_credentials_allowed is not False: raise ValueError("Matching result is always isolated.")
    def canonical_payload(self) -> dict[str, object]: return {"state": self.state.value, "request_hash": self.request_hash, "fill_hashes": [item.fill_hash for item in self.fills], "ledger_hash": self.ledger.ledger_hash, "reason_codes": list(self.reason_codes), "audit_hash": self.audit_event.audit_hash, "dry_run": True, "live_order_allowed": False, "broker_connected": False, "account_credentials_allowed": False}
    @property
    def result_hash(self) -> str: return _hash(self.canonical_payload())


def _result(request: PaperTradingOrderRequest, state: PaperTradingMatchState, ledger: PaperTradingLedger, *, snapshot: OfflineMarketSnapshot | None = None, fills: tuple[PaperTradingFill, ...] = (), transaction: PaperTradingLedgerTransaction | None = None, reasons: tuple[str, ...] = ()) -> PaperTradingMatchingResult:
    event = PaperTradingMatchingAudit(f"order_{state.value}", request.request_hash, snapshot.snapshot_hash if snapshot else None, tuple(sorted(fill.fill_hash for fill in fills)), tuple(sorted(set(reasons))), snapshot.observed_at if snapshot else request.created_at)
    return PaperTradingMatchingResult(state, request.request_hash, fills, ledger, transaction, tuple(sorted(set(reasons))), event)


def match_paper_trading_order(request: PaperTradingOrderRequest, order_type: PaperTradingOrderType, book: InMemoryPaperOrderBook, ledger: PaperTradingLedger, safety_state: PaperTradingSafetyState, *, fee_rate: Decimal = Decimal("0")) -> PaperTradingMatchingResult:
    """Match one paper request solely against a supplied in-memory snapshot."""
    safety = evaluate_paper_trading_order(request, safety_state)
    if safety.state.value == "rejected": return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=safety.reason_codes)
    if request.idempotency_key in ledger.used_idempotency_keys: return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=("DUPLICATE_IDEMPOTENCY_KEY",))
    if safety_state.emergency_stop: return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=("EMERGENCY_STOP",))
    if not isinstance(fee_rate, Decimal) or not fee_rate.is_finite() or fee_rate < 0: return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=("INVALID_FEE_RATE",))
    snapshot = book.snapshot_for(request.instrument)
    if snapshot is None: return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=("SNAPSHOT_UNAVAILABLE",))
    price = snapshot.ask_price if request.side is PaperTradingSide.BUY else snapshot.bid_price
    available = snapshot.available_ask_quantity if request.side is PaperTradingSide.BUY else snapshot.available_bid_quantity
    crosses = order_type is PaperTradingOrderType.MARKET or (request.side is PaperTradingSide.BUY and request.price >= price) or (request.side is PaperTradingSide.SELL and request.price <= price)
    if not crosses:
        return _result(request, PaperTradingMatchState.OPEN, reserve_idempotency_key(ledger, request.idempotency_key), snapshot=snapshot)
    quantity = min(request.quantity, available)
    fees = (quantity * price * fee_rate)
    fill = PaperTradingFill(_hash({"request": request.request_hash, "snapshot": snapshot.snapshot_hash, "quantity": str(quantity)})[:32], request.idempotency_key, request.instrument, request.side, quantity, price, fees, snapshot.observed_at)
    try:
        transaction = apply_paper_fill(ledger, fill)
        updated = reserve_idempotency_key(transaction.ledger, request.idempotency_key)
        transaction = PaperTradingLedgerTransaction(updated, transaction.cash_entry)
    except ValueError as error:
        return _result(request, PaperTradingMatchState.REJECTED, ledger, snapshot=snapshot, reasons=(str(error),))
    state = PaperTradingMatchState.FILLED if quantity == request.quantity else PaperTradingMatchState.PARTIALLY_FILLED
    return _result(request, state, updated, snapshot=snapshot, fills=(fill,), transaction=transaction)


def cancel_paper_trading_order(request: PaperTradingOrderRequest, ledger: PaperTradingLedger) -> PaperTradingMatchingResult:
    """Locally cancel an unfilled paper request; no external action exists."""
    if request.idempotency_key in ledger.used_idempotency_keys: return _result(request, PaperTradingMatchState.REJECTED, ledger, reasons=("DUPLICATE_IDEMPOTENCY_KEY",))
    return _result(request, PaperTradingMatchState.CANCELLED, reserve_idempotency_key(ledger, request.idempotency_key), reasons=("CANCELLED_LOCALLY",))
