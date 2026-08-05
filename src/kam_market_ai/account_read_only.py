"""Offline-only futures account read model; it has no broker or order capability."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Protocol


class AccountDataFreshness(StrEnum):
    DEMO = "DEMO"
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class CapitalSafetyLevel(StrEnum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    DANGER = "DANGER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AccountFunds:
    equity: Decimal | None
    available_margin: Decimal | None
    initial_margin: Decimal | None
    used_margin: Decimal | None
    maintenance_margin: Decimal | None
    unrealized_pnl: Decimal | None
    today_realized_pnl: Decimal | None


@dataclass(frozen=True, slots=True)
class MarginUsage:
    usage_ratio: Decimal | None


@dataclass(frozen=True, slots=True)
class AccountPositionSummary:
    product_code: str
    label: str
    quantity: Decimal | None
    side: str | None
    unrealized_pnl: Decimal | None
    average_price: Decimal | None = None
    market_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.product_code not in {"TX", "MTX", "TMF"}:
            raise ValueError("Only TX, MTX, and TMF summaries are supported.")


@dataclass(frozen=True, slots=True)
class CapitalSafetyThresholds:
    """Injected policy, never a value encoded in the UI."""
    caution_usage_ratio: Decimal
    danger_usage_ratio: Decimal
    initial_margin_multiplier: Decimal = Decimal("1")
    minimum_free_margin: Decimal = Decimal("0")
    maximum_margin_usage_ratio: Decimal = Decimal("1")
    warning_buffer_amount: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not (Decimal("0") < self.caution_usage_ratio < self.danger_usage_ratio <= Decimal("1")):
            raise ValueError("Capital safety thresholds must be ordered ratios in (0, 1].")
        if self.initial_margin_multiplier < Decimal("1") or self.minimum_free_margin < 0 or self.warning_buffer_amount < 0:
            raise ValueError("Capital safety thresholds cannot weaken the minimum margin requirement.")
        if not (Decimal("0") < self.maximum_margin_usage_ratio <= Decimal("1")):
            raise ValueError("maximum_margin_usage_ratio must be in (0, 1].")


@dataclass(frozen=True, slots=True)
class CapitalSafetyAssessment:
    level: CapitalSafetyLevel
    reason: str
    usage_ratio: Decimal | None
    required_initial_margin: Decimal | None = None
    required_maintenance_margin: Decimal | None = None
    distance_to_caution: Decimal | None = None
    distance_to_danger: Decimal | None = None
    margin_effective_at: datetime | None = None
    margin_source: str | None = None


@dataclass(frozen=True, slots=True)
class MarginRequirement:
    product_code: str
    initial_margin: Decimal
    maintenance_margin: Decimal
    effective_at: datetime
    source: str
    fetched_at: datetime
    freshness: AccountDataFreshness

    def __post_init__(self) -> None:
        if self.product_code not in {"TX", "MTX", "TMF"} or self.initial_margin <= 0 or self.maintenance_margin <= 0:
            raise ValueError("Margin requirements must be positive TX, MTX, or TMF values.")
        if self.effective_at.tzinfo is None or self.fetched_at.tzinfo is None:
            raise ValueError("Margin requirement timestamps must be timezone-aware.")


class MarginRequirementSource(Protocol):
    """Independent read-only margin data source with no account or order capability."""

    def read_requirements(self) -> tuple[MarginRequirement, ...]: ...


@dataclass(frozen=True, slots=True)
class FuturesAccountSnapshot:
    account_status: str
    account_masked: str
    funds: AccountFunds
    margin_usage: MarginUsage
    positions: tuple[AccountPositionSummary, ...]
    source: str
    updated_at: datetime | None
    freshness: AccountDataFreshness
    account_connected: bool = False
    live_order_allowed: bool = False
    broker_connected: bool = False
    trading_enabled: bool = False
    emergency_stop: bool = False

    def __post_init__(self) -> None:
        if self.live_order_allowed or self.broker_connected or self.trading_enabled:
            raise ValueError("Account read-only snapshots cannot enable trading or broker connectivity.")
        if self.updated_at is not None and (self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None):
            raise ValueError("updated_at must be UTC timezone-aware when supplied.")
        if any(item.product_code not in {"TX", "MTX", "TMF"} for item in self.positions):
            raise ValueError("Position summaries must be futures product summaries.")

    @property
    def snapshot_hash(self) -> str:
        payload = repr((self.account_status, self.account_masked, self.funds, self.margin_usage, self.positions, self.source, self.updated_at, self.freshness, self.account_connected, self.emergency_stop))
        return sha256(payload.encode("utf-8")).hexdigest()


class AccountReadOnlySource(Protocol):
    """A source can only return a snapshot; it intentionally exposes no order client."""

    def read_snapshot(self) -> FuturesAccountSnapshot: ...


def calculate_required_margins(positions: tuple[AccountPositionSummary, ...], margin_source: MarginRequirementSource) -> tuple[Decimal, Decimal] | None:
    """Sum absolute quantities across all supplied futures positions."""
    requirements = {item.product_code: item for item in margin_source.read_requirements()}
    if set(requirements) != {"TX", "MTX", "TMF"} or any(item.freshness not in {AccountDataFreshness.FRESH, AccountDataFreshness.DEMO} for item in requirements.values()):
        return None
    if any(position.quantity is None or position.product_code not in requirements for position in positions):
        return None
    initial = sum(abs(position.quantity or Decimal("0")) * requirements[position.product_code].initial_margin for position in positions)
    maintenance = sum(abs(position.quantity or Decimal("0")) * requirements[position.product_code].maintenance_margin for position in positions)
    return initial, maintenance


def assess_capital_safety(snapshot: FuturesAccountSnapshot, thresholds: CapitalSafetyThresholds, margin_source: MarginRequirementSource | None = None) -> CapitalSafetyAssessment:
    """Fail closed: missing, stale, or disconnected data can never be SAFE."""
    if not snapshot.account_connected:
        return CapitalSafetyAssessment(CapitalSafetyLevel.UNKNOWN, "帳戶來源尚未連線", None)
    if snapshot.freshness is not AccountDataFreshness.FRESH or margin_source is None:
        return CapitalSafetyAssessment(CapitalSafetyLevel.UNKNOWN, "資料不足或已過期", None)
    if snapshot.funds.equity is None or snapshot.funds.available_margin is None:
        return CapitalSafetyAssessment(CapitalSafetyLevel.UNKNOWN, "帳戶權益或可動用保證金不完整", None)
    requirements = {item.product_code: item for item in margin_source.read_requirements()}
    if set(requirements) != {"TX", "MTX", "TMF"} or any(item.freshness is not AccountDataFreshness.FRESH for item in requirements.values()):
        return CapitalSafetyAssessment(CapitalSafetyLevel.UNKNOWN, "保證金資料缺失或過期", None)
    if any(position.quantity is None or position.product_code not in requirements for position in snapshot.positions):
        return CapitalSafetyAssessment(CapitalSafetyLevel.UNKNOWN, "帳戶部位資料不完整", None)
    initial = sum(abs(position.quantity or Decimal("0")) * requirements[position.product_code].initial_margin for position in snapshot.positions)
    maintenance = sum(abs(position.quantity or Decimal("0")) * requirements[position.product_code].maintenance_margin for position in snapshot.positions)
    equity, free = snapshot.funds.equity, snapshot.funds.available_margin
    usage = initial / equity if equity > 0 else Decimal("1")
    effective_at = min(item.effective_at for item in requirements.values())
    source = ", ".join(sorted({item.source for item in requirements.values()}))
    caution_floor = max(
        initial * thresholds.initial_margin_multiplier + thresholds.warning_buffer_amount,
        initial,
    )
    common = dict(usage_ratio=usage, required_initial_margin=initial, required_maintenance_margin=maintenance, distance_to_caution=equity - caution_floor, distance_to_danger=equity - maintenance, margin_effective_at=effective_at, margin_source=source)
    if equity <= maintenance or free <= 0:
        return CapitalSafetyAssessment(CapitalSafetyLevel.DANGER, "帳戶權益低於維持保證金或可動用保證金不足", **common)
    if (
        equity <= caution_floor
        or free < thresholds.minimum_free_margin
        or usage >= thresholds.maximum_margin_usage_ratio
        or usage >= thresholds.caution_usage_ratio
    ):
        return CapitalSafetyAssessment(CapitalSafetyLevel.CAUTION, "帳戶資金未符合安全緩衝門檻", **common)
    return CapitalSafetyAssessment(CapitalSafetyLevel.SAFE, "帳戶權益與安全緩衝均符合門檻", **common)


@dataclass(frozen=True, slots=True)
class DemoAccountReadOnlySource:
    """Explicit local fixture. It cannot claim a connected real futures account."""
    snapshot: FuturesAccountSnapshot

    def read_snapshot(self) -> FuturesAccountSnapshot:
        return self.snapshot


@dataclass(frozen=True, slots=True)
class DemoMarginRequirementSource:
    """Explicit, replaceable offline margin snapshot for presentation tests."""
    requirements: tuple[MarginRequirement, ...]

    def read_requirements(self) -> tuple[MarginRequirement, ...]:
        return self.requirements


DEMO_ACCOUNT_THRESHOLDS = CapitalSafetyThresholds(Decimal("0.50"), Decimal("0.75"))
_DEMO_MARGIN_TIME = datetime(2026, 8, 5, tzinfo=UTC)
DEMO_MARGIN_SOURCE = DemoMarginRequirementSource((
    MarginRequirement("TX", Decimal("636000"), Decimal("488000"), _DEMO_MARGIN_TIME, "offline-demo-margin-snapshot", _DEMO_MARGIN_TIME, AccountDataFreshness.DEMO),
    MarginRequirement("MTX", Decimal("159000"), Decimal("122000"), _DEMO_MARGIN_TIME, "offline-demo-margin-snapshot", _DEMO_MARGIN_TIME, AccountDataFreshness.DEMO),
    MarginRequirement("TMF", Decimal("31800"), Decimal("24400"), _DEMO_MARGIN_TIME, "offline-demo-margin-snapshot", _DEMO_MARGIN_TIME, AccountDataFreshness.DEMO),
))
DEMO_ACCOUNT_SOURCE = DemoAccountReadOnlySource(FuturesAccountSnapshot(
    account_status="示範帳戶・尚未連線",
    account_masked="••••-DEMO",
    funds=AccountFunds(Decimal("1000000"), Decimal("800000"), Decimal("200000"), Decimal("0"), Decimal("160000"), Decimal("0"), Decimal("0")),
    margin_usage=MarginUsage(Decimal("0")),
    positions=(
        AccountPositionSummary("TX", "大台 TX", Decimal("0"), None, Decimal("0")),
        AccountPositionSummary("MTX", "小台 MTX", Decimal("0"), None, Decimal("0")),
        AccountPositionSummary("TMF", "微台 TMF", Decimal("0"), None, Decimal("0")),
    ),
    source="offline-demo-account-snapshot",
    updated_at=datetime(2026, 8, 5, tzinfo=UTC),
    freshness=AccountDataFreshness.DEMO,
))
