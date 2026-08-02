"""Immutable cash and position ledger for isolated Paper Trading fills."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from json import dumps

from .contracts import PaperTradingFill, PaperTradingPosition, PaperTradingSide


def _decimal(value: Decimal, field_name: str, *, non_negative: bool = False) -> str:
    if not isinstance(value, Decimal) or not value.is_finite(): raise ValueError(f"{field_name} must be a finite Decimal.")
    if non_negative and value < 0: raise ValueError(f"{field_name} must be non-negative.")
    return str(value)


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperTradingCashLedgerEntry:
    entry_id: str
    fill_id: str
    cash_delta: Decimal
    fees: Decimal
    balance_after: Decimal

    def __post_init__(self) -> None:
        if not self.entry_id or not self.fill_id: raise ValueError("Cash entry identity is required.")
        _decimal(self.cash_delta, "cash_delta"); _decimal(self.fees, "fees", non_negative=True); _decimal(self.balance_after, "balance_after", non_negative=True)

    def canonical_payload(self) -> dict[str, str]:
        return {"entry_id": self.entry_id, "fill_id": self.fill_id, "cash_delta": _decimal(self.cash_delta, "cash_delta"), "fees": _decimal(self.fees, "fees"), "balance_after": _decimal(self.balance_after, "balance_after", non_negative=True)}


@dataclass(frozen=True, slots=True)
class PaperTradingLedger:
    cash_balance: Decimal
    positions: tuple[PaperTradingPosition, ...] = ()
    cash_entries: tuple[PaperTradingCashLedgerEntry, ...] = ()
    used_idempotency_keys: tuple[str, ...] = ()
    allow_negative_cash: bool = False
    allow_short: bool = False
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        _decimal(self.cash_balance, "cash_balance", non_negative=not self.allow_negative_cash)
        instruments = tuple(item.instrument for item in self.positions)
        if instruments != tuple(sorted(set(instruments))): raise ValueError("Positions must be unique and canonical ordered.")
        if any(item.quantity < 0 for item in self.positions) and not self.allow_short: raise ValueError("Short positions are not allowed.")
        entry_ids = tuple(item.entry_id for item in self.cash_entries)
        if len(entry_ids) != len(set(entry_ids)): raise ValueError("Cash entries must have unique IDs.")
        if self.used_idempotency_keys != tuple(sorted(set(self.used_idempotency_keys))): raise ValueError("Idempotency keys must be unique and canonical ordered.")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.account_credentials_allowed is not False: raise ValueError("Ledger is always isolated.")

    def canonical_payload(self) -> dict[str, object]:
        return {"cash_balance": _decimal(self.cash_balance, "cash_balance", non_negative=not self.allow_negative_cash), "positions": [item.canonical_payload() for item in self.positions], "cash_entries": [item.canonical_payload() for item in self.cash_entries], "used_idempotency_keys": list(self.used_idempotency_keys), "allow_negative_cash": self.allow_negative_cash, "allow_short": self.allow_short, "dry_run": True, "live_order_allowed": False, "broker_connected": False, "account_credentials_allowed": False}

    @property
    def ledger_hash(self) -> str: return _hash(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class PaperTradingLedgerTransaction:
    ledger: PaperTradingLedger
    cash_entry: PaperTradingCashLedgerEntry | None


def reserve_idempotency_key(ledger: PaperTradingLedger, key: str) -> PaperTradingLedger:
    if key in ledger.used_idempotency_keys: raise ValueError("DUPLICATE_IDEMPOTENCY_KEY")
    return PaperTradingLedger(ledger.cash_balance, ledger.positions, ledger.cash_entries, tuple(sorted((*ledger.used_idempotency_keys, key))), ledger.allow_negative_cash, ledger.allow_short)


def apply_paper_fill(ledger: PaperTradingLedger, fill: PaperTradingFill) -> PaperTradingLedgerTransaction:
    """Apply exactly one fill atomically or raise without changing the source ledger."""
    positions = {item.instrument: item for item in ledger.positions}
    notional = fill.quantity * fill.price
    if fill.side is PaperTradingSide.BUY:
        debit = notional + fill.fees
        if not ledger.allow_negative_cash and ledger.cash_balance < debit: raise ValueError("INSUFFICIENT_CASH")
        balance = ledger.cash_balance - debit
        old = positions.get(fill.instrument)
        quantity = fill.quantity + (old.quantity if old else Decimal("0"))
        average = fill.price if old is None else ((old.quantity * old.average_price) + notional) / quantity
        positions[fill.instrument] = PaperTradingPosition(fill.instrument, quantity, average, old.realized_pnl if old else Decimal("0"), fill.filled_at)
        delta = -debit
    else:
        old = positions.get(fill.instrument)
        if old is None or (not ledger.allow_short and old.quantity < fill.quantity): raise ValueError("INSUFFICIENT_POSITION")
        quantity = (old.quantity if old else Decimal("0")) - fill.quantity
        balance = ledger.cash_balance + notional - fill.fees
        if quantity == 0: positions.pop(fill.instrument, None)
        else: positions[fill.instrument] = PaperTradingPosition(fill.instrument, quantity, old.average_price, old.realized_pnl + ((fill.price - old.average_price) * fill.quantity) - fill.fees, fill.filled_at)
        delta = notional - fill.fees
    entry = PaperTradingCashLedgerEntry(fill.fill_id, fill.fill_id, delta, fill.fees, balance)
    updated = PaperTradingLedger(balance, tuple(sorted(positions.values(), key=lambda item: item.instrument)), (*ledger.cash_entries, entry), ledger.used_idempotency_keys, ledger.allow_negative_cash, ledger.allow_short)
    return PaperTradingLedgerTransaction(updated, entry)
