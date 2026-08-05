"""Deterministic, offline-only strategy-to-paper-order proposal contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps


PAPER_ORDER_PROPOSAL_VERSION = "0.1"


class PaperOrderProposalAction(StrEnum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    HOLD = "hold"


class PaperOrderProposalOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class PaperOrderProposalRiskStatus(StrEnum):
    ACCEPTABLE = "acceptable"
    CAUTION = "caution"
    BLOCKED = "blocked"


class ManualConfirmationStatus(StrEnum):
    REQUIRED = "required"
    NOT_APPLICABLE = "not_applicable"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC timezone-aware.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None, field: str, *, positive: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite() or positive and value <= 0:
        raise ValueError(f"{field} must be a finite positive Decimal.")
    return str(value)


def _hash(payload: object) -> str:
    return sha256(dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperOrderProposalReason:
    code: str
    text: str
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.code or not self.text or self.priority < 0:
            raise ValueError("Proposal reason must be complete.")

    def canonical_payload(self) -> dict[str, object]:
        return {"code": self.code, "text": self.text, "priority": self.priority}


@dataclass(frozen=True, slots=True)
class PaperOrderProposalRisk:
    status: PaperOrderProposalRiskStatus
    detail: str
    blocked: bool = False

    def __post_init__(self) -> None:
        if not self.detail or self.blocked != (self.status is PaperOrderProposalRiskStatus.BLOCKED):
            raise ValueError("Proposal risk status is inconsistent.")

    def canonical_payload(self) -> dict[str, object]:
        return {"status": self.status.value, "detail": self.detail, "blocked": self.blocked}


@dataclass(frozen=True, slots=True)
class PaperOrderProposalInput:
    proposal_id: str
    strategy_version: str
    instrument: str
    action: PaperOrderProposalAction
    order_type: PaperOrderProposalOrderType | None
    quantity: Decimal | None
    reference_price: Decimal
    limit_price: Decimal | None
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    confidence: Decimal
    risk: PaperOrderProposalRisk
    reasons: tuple[PaperOrderProposalReason, ...]
    generated_at: datetime
    expires_at: datetime
    source_hash: str
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    trading_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.proposal_id or not self.strategy_version or not self.source_hash:
            raise ValueError("Proposal identity and source hash are required.")
        if not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("Instrument must be canonical.")
        _decimal(self.reference_price, "reference_price", positive=True)
        _decimal(self.confidence, "confidence")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be from 0 to 1.")
        _utc(self.generated_at, "generated_at"); _utc(self.expires_at, "expires_at")
        if self.expires_at <= self.generated_at:
            raise ValueError("expires_at must follow generated_at.")
        reasons = tuple(sorted(self.reasons, key=lambda item: (item.priority, item.code, item.text)))
        if not reasons or reasons != self.reasons or len({item.code for item in reasons}) != len(reasons):
            raise ValueError("Reasons must be non-empty, unique and canonical ordered.")
        if self.dry_run is not True or self.live_order_allowed is not False or self.broker_connected is not False or self.trading_enabled is not False:
            raise ValueError("Paper proposals are always offline and disabled for live trading.")
        if self.action is PaperOrderProposalAction.HOLD:
            if any(value is not None for value in (self.order_type, self.quantity, self.limit_price, self.stop_loss_price, self.take_profit_price)):
                raise ValueError("HOLD must not contain an order.")
        else:
            if self.order_type is None or self.quantity is None:
                raise ValueError("An actionable proposal requires order type and quantity.")
            _decimal(self.quantity, "quantity", positive=True)
            _decimal(self.limit_price, "limit_price", positive=self.order_type is PaperOrderProposalOrderType.LIMIT)
            _decimal(self.stop_loss_price, "stop_loss_price", positive=True)
            _decimal(self.take_profit_price, "take_profit_price", positive=True)
            if self.stop_loss_price is None or self.take_profit_price is None:
                raise ValueError("Actionable proposal requires stop loss and take profit.")
            if self.action is PaperOrderProposalAction.BUY and not (self.stop_loss_price < self.reference_price < self.take_profit_price):
                raise ValueError("BUY protection prices are invalid.")
            if self.action is PaperOrderProposalAction.SELL and not (self.take_profit_price < self.reference_price < self.stop_loss_price):
                raise ValueError("SELL protection prices are invalid.")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id, "strategy_version": self.strategy_version, "instrument": self.instrument,
            "action": self.action.value, "order_type": self.order_type.value if self.order_type else None,
            "quantity": _decimal(self.quantity, "quantity", positive=True) if self.quantity else None,
            "reference_price": _decimal(self.reference_price, "reference_price", positive=True),
            "limit_price": _decimal(self.limit_price, "limit_price"), "stop_loss_price": _decimal(self.stop_loss_price, "stop_loss_price"),
            "take_profit_price": _decimal(self.take_profit_price, "take_profit_price"), "confidence": _decimal(self.confidence, "confidence"),
            "risk": self.risk.canonical_payload(), "reasons": [item.canonical_payload() for item in self.reasons],
            "generated_at": _utc(self.generated_at, "generated_at"), "expires_at": _utc(self.expires_at, "expires_at"),
            "source_hash": self.source_hash, "dry_run": True, "live_order_allowed": False, "broker_connected": False, "trading_enabled": False,
        }


@dataclass(frozen=True, slots=True)
class PaperOrderProposal:
    input: PaperOrderProposalInput
    manual_confirmation_status: ManualConfirmationStatus
    proposal_version: str = PAPER_ORDER_PROPOSAL_VERSION

    def __post_init__(self) -> None:
        expected = ManualConfirmationStatus.NOT_APPLICABLE if self.input.action is PaperOrderProposalAction.HOLD else ManualConfirmationStatus.REQUIRED
        if self.proposal_version != PAPER_ORDER_PROPOSAL_VERSION or self.manual_confirmation_status is not expected:
            raise ValueError("Proposal status must be derived from action.")

    @property
    def proposal_hash(self) -> str:
        return _hash({"version": self.proposal_version, "input": self.input.canonical_payload(), "manual_confirmation_status": self.manual_confirmation_status.value})

    def canonical_payload(self) -> dict[str, object]:
        return {**self.input.canonical_payload(), "proposal_version": self.proposal_version, "proposal_hash": self.proposal_hash, "manual_confirmation_status": self.manual_confirmation_status.value}


@dataclass(frozen=True, slots=True)
class PaperOrderProposalAuditEvent:
    proposal_hash: str
    event_type: str
    occurred_at: datetime
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.event_type not in {"proposal_generated", "proposal_confirmed", "proposal_rejected", "proposal_expired"}:
            raise ValueError("Unknown proposal audit event.")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Audit codes must be canonical.")
        _utc(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class PaperOrderProposalResult:
    proposal: PaperOrderProposal | None
    status: ManualConfirmationStatus
    reason_codes: tuple[str, ...]
    audit_event: PaperOrderProposalAuditEvent

    def __post_init__(self) -> None:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("Result codes must be canonical.")


def build_paper_order_proposal(value: PaperOrderProposalInput) -> PaperOrderProposalResult:
    if not isinstance(value, PaperOrderProposalInput):
        raise TypeError("PaperOrderProposalInput is required.")
    proposal = PaperOrderProposal(value, ManualConfirmationStatus.NOT_APPLICABLE if value.action is PaperOrderProposalAction.HOLD else ManualConfirmationStatus.REQUIRED)
    return PaperOrderProposalResult(proposal, proposal.manual_confirmation_status, (), PaperOrderProposalAuditEvent(proposal.proposal_hash, "proposal_generated", value.generated_at))
