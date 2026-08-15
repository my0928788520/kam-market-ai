"""Paper-only TMF simulation driven by verified five-timeframe market data.

The module is deliberately downstream from the read-only market-data pipeline.
It accepts only normalized candles or an already evaluated canonical paper
direction, never imports a broker client, and never exposes an order endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps, loads
from os import replace
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from kam_market_ai.live_read_only.five_timeframe_analysis_preview import (
    build_verified_five_timeframe_analysis_preview,
)
from kam_market_ai.market_data.fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)

from .contracts import (
    PaperTradingAccountSnapshot,
    PaperTradingFill,
    PaperTradingOrderRequest,
    PaperTradingPosition,
    PaperTradingRiskLimits,
    PaperTradingSafetyState,
    PaperTradingSide,
)
from .five_timeframe_paper_direction import FiveTimeframePaperDirection
from .ledger import (
    PaperTradingCashLedgerEntry,
    PaperTradingLedger,
)
from .matching_engine import (
    InMemoryPaperOrderBook,
    OfflineMarketSnapshot,
    PaperTradingMatchState,
    PaperTradingOrderType,
    match_paper_trading_order,
)
from .order_proposal import (
    PaperOrderProposalAction,
    PaperOrderProposalInput,
    PaperOrderProposalOrderType,
    PaperOrderProposalReason,
    PaperOrderProposalRisk,
    PaperOrderProposalRiskStatus,
    build_paper_order_proposal,
)
from .proposal_runner import (
    PaperOrderProposalRunnerState,
    confirm_paper_order_proposal,
)

LIVE_TMF_PAPER_SIMULATION_VERSION = "0.2"
LIVE_TMF_PAPER_JOURNAL_SCHEMA = "kam-live-tmf-paper-journal-v2"
LEGACY_TMF_PAPER_SIMULATION_VERSION = "0.1"
LEGACY_TMF_PAPER_JOURNAL_SCHEMA = "kam-live-tmf-paper-journal-v1"
TAIWAN_RISK_TIMEZONE = ZoneInfo("Asia/Taipei")
TAIWAN_RISK_DAY_BOUNDARY_HOUR = 6
MINIMUM_PERFORMANCE_SAMPLE_SIZE = 30


def _hash(payload: object) -> str:
    return sha256(
        dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _utc(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC timezone-aware.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO timestamp.")
    parsed = datetime.fromisoformat(value)
    _utc(parsed, field)
    return parsed


def _decimal(value: Decimal, field: str, *, positive: bool = False) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal.")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive.")
    return str(value)


def _taiwan_risk_day(value: datetime) -> str:
    """Group day and after-hours activity into one Taiwan futures risk day."""
    _utc(value, "risk_day_timestamp")
    shifted = value.astimezone(TAIWAN_RISK_TIMEZONE) - timedelta(
        hours=TAIWAN_RISK_DAY_BOUNDARY_HOUR
    )
    return shifted.date().isoformat()


class TmfPaperCycleAction(StrEnum):
    HOLD = "hold"
    PENDING_MANUAL_CONFIRMATION = "pending_manual_confirmation"
    ENTRY_FILLED = "entry_filled"
    POSITION_MARKED = "position_marked"
    EXIT_FILLED = "exit_filled"
    DUPLICATE_IGNORED = "duplicate_ignored"
    REJECTED = "rejected"


class TmfPaperPerformanceEventType(StrEnum):
    ENTRY = "entry"
    MARK = "mark"
    STOP_LOSS_EXIT = "stop_loss_exit"
    TAKE_PROFIT_EXIT = "take_profit_exit"


class TmfPaperMarginStatus(StrEnum):
    NO_POSITION = "no_position"
    SAFE = "safe"
    MAINTENANCE_WARNING = "maintenance_warning"


@dataclass(frozen=True, slots=True)
class TmfPaperMarginRequirement:
    initial_margin: Decimal
    maintenance_margin: Decimal
    effective_at: datetime
    source: str

    def __post_init__(self) -> None:
        _decimal(self.initial_margin, "initial_margin", positive=True)
        _decimal(self.maintenance_margin, "maintenance_margin", positive=True)
        if self.initial_margin < self.maintenance_margin:
            raise ValueError("initial margin must cover maintenance margin.")
        _utc(self.effective_at, "margin_effective_at")
        if not self.source or self.source != self.source.strip():
            raise ValueError("margin source is required.")

    def canonical_payload(self) -> dict[str, str]:
        return {
            "initial_margin": _decimal(
                self.initial_margin,
                "initial_margin",
                positive=True,
            ),
            "maintenance_margin": _decimal(
                self.maintenance_margin,
                "maintenance_margin",
                positive=True,
            ),
            "effective_at": _utc(self.effective_at, "margin_effective_at"),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class TmfPaperSimulationConfig:
    instrument: str = "TMF"
    quantity: Decimal = Decimal(1)
    point_value: Decimal = Decimal(10)
    tick_size: Decimal = Decimal(1)
    stop_loss_points: Decimal = Decimal(20)
    take_profit_points: Decimal = Decimal(40)
    trend_hold_enabled: bool = True
    take_profit_extension_points: Decimal = Decimal(20)
    initial_cash: Decimal = Decimal(1000000)
    max_order_notional: Decimal = Decimal(1000000)
    max_daily_loss: Decimal = Decimal(10000)
    max_entries_per_risk_day: int = 3
    max_quote_age_seconds: int = 360
    reentry_cooldown_minutes: int = 15
    entry_confirmation_candles: int = 1
    max_entry_confirmation_move_points: Decimal = Decimal(20)
    initial_margin: Decimal = Decimal(35050)
    maintenance_margin: Decimal = Decimal(26900)
    margin_effective_at: datetime = datetime(2026, 8, 12, 5, 45, tzinfo=UTC)
    margin_source: str = "TAIFEX_INDEX_MARGIN_2026-08-12"
    paper_trading_enabled: bool = False
    manual_approval_granted: bool = False
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("instrument must be a canonical futures symbol.")
        for field, value in (
            ("quantity", self.quantity),
            ("point_value", self.point_value),
            ("tick_size", self.tick_size),
            ("stop_loss_points", self.stop_loss_points),
            ("take_profit_points", self.take_profit_points),
            ("take_profit_extension_points", self.take_profit_extension_points),
            (
                "max_entry_confirmation_move_points",
                self.max_entry_confirmation_move_points,
            ),
            ("initial_cash", self.initial_cash),
            ("max_order_notional", self.max_order_notional),
            ("max_daily_loss", self.max_daily_loss),
            ("initial_margin", self.initial_margin),
            ("maintenance_margin", self.maintenance_margin),
        ):
            _decimal(value, field, positive=True)
        if self.initial_margin < self.maintenance_margin:
            raise ValueError("initial margin must cover maintenance margin.")
        _utc(self.margin_effective_at, "margin_effective_at")
        if not self.margin_source or self.margin_source != self.margin_source.strip():
            raise ValueError("margin_source is required.")
        if self.quantity > Decimal(1):
            raise ValueError("TMF paper simulation is limited to one contract.")
        if (
            self.stop_loss_points % self.tick_size != 0
            or self.take_profit_points % self.tick_size != 0
            or self.take_profit_extension_points % self.tick_size != 0
            or self.max_entry_confirmation_move_points % self.tick_size != 0
        ):
            raise ValueError("Protection distances must align to the TMF tick size.")
        if isinstance(self.max_quote_age_seconds, bool) or self.max_quote_age_seconds <= 0:
            raise ValueError("max_quote_age_seconds must be positive.")
        if (
            isinstance(self.max_entries_per_risk_day, bool)
            or self.max_entries_per_risk_day <= 0
        ):
            raise ValueError("max_entries_per_risk_day must be positive.")
        if (
            isinstance(self.reentry_cooldown_minutes, bool)
            or self.reentry_cooldown_minutes < 0
        ):
            raise ValueError("reentry_cooldown_minutes must be zero or positive.")
        if (
            isinstance(self.entry_confirmation_candles, bool)
            or self.entry_confirmation_candles <= 0
        ):
            raise ValueError("entry_confirmation_candles must be positive.")
        if (
            self.dry_run is not True
            or self.live_order_allowed is not False
            or self.broker_connected is not False
            or self.account_credentials_allowed is not False
        ):
            raise ValueError("TMF simulation is permanently isolated from live trading.")

    @property
    def margin_requirement(self) -> TmfPaperMarginRequirement:
        return TmfPaperMarginRequirement(
            self.initial_margin,
            self.maintenance_margin,
            self.margin_effective_at,
            self.margin_source,
        )


@dataclass(frozen=True, slots=True)
class TmfPaperQuote:
    instrument: str
    price: Decimal
    observed_at: datetime
    source_hash: str
    price_policy: str = "LATEST_VERIFIED_5M_CLOSE"
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.strip().upper():
            raise ValueError("quote instrument must be canonical.")
        _decimal(self.price, "price", positive=True)
        _utc(self.observed_at, "observed_at")
        if len(self.source_hash) != 64 or self.price_policy != "LATEST_VERIFIED_5M_CLOSE":
            raise ValueError("verified quote identity is required.")
        if self.dry_run is not True or self.live_order_allowed or self.broker_connected:
            raise ValueError("paper quote cannot enable broker execution.")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "instrument": self.instrument,
            "price": _decimal(self.price, "price", positive=True),
            "observed_at": _utc(self.observed_at, "observed_at"),
            "source_hash": self.source_hash,
            "price_policy": self.price_policy,
            "dry_run": True,
            "live_order_allowed": False,
            "broker_connected": False,
        }

    @property
    def quote_hash(self) -> str:
        return _hash(self.canonical_payload())


def build_tmf_paper_quote(
    value: CompleteFiveTimeframeCandleResult | FiveTimeframeCandleResult,
    *,
    instrument: str,
) -> TmfPaperQuote:
    """Build a provider-neutral paper quote from the latest normalized 5m close."""
    if not isinstance(value, (CompleteFiveTimeframeCandleResult, FiveTimeframeCandleResult)):
        raise TypeError("five-timeframe candle result is required.")
    if FiveTimeframe.M5 not in value.series or not value.series[FiveTimeframe.M5]:
        raise ValueError("TMF_5M_QUOTE_UNAVAILABLE")
    latest = value.series[FiveTimeframe.M5][-1]
    if latest.instrument.value != "TMF":
        raise ValueError("TMF_INSTRUMENT_REQUIRED")
    payload = {
        "instrument": instrument,
        "candle_instrument": latest.instrument.value,
        "start": latest.start.isoformat(),
        "end": latest.end.isoformat(),
        "open": str(latest.open),
        "high": str(latest.high),
        "low": str(latest.low),
        "close": str(latest.close),
        "volume": latest.volume,
    }
    return TmfPaperQuote(
        instrument,
        Decimal(str(latest.close)),
        latest.end.astimezone(UTC),
        _hash(payload),
    )


@dataclass(frozen=True, slots=True)
class TmfPaperPerformanceEvent:
    event_type: TmfPaperPerformanceEventType
    trade_id: str
    instrument: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    max_favorable_excursion: Decimal
    max_adverse_excursion: Decimal
    observed_at: datetime
    quote_hash: str
    proposal_hash: str
    fill_hash: str | None
    previous_event_hash: str | None
    point_value: Decimal = Decimal(10)
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.trade_id or not self.instrument or self.instrument != self.instrument.upper():
            raise ValueError("performance event identity is required.")
        for field, value in (
            ("quantity", self.quantity),
            ("entry_price", self.entry_price),
            ("current_price", self.current_price),
            ("stop_loss_price", self.stop_loss_price),
            ("take_profit_price", self.take_profit_price),
            ("point_value", self.point_value),
        ):
            _decimal(value, field, positive=True)
        for field, value in (
            ("unrealized_pnl", self.unrealized_pnl),
            ("realized_pnl", self.realized_pnl),
            ("max_favorable_excursion", self.max_favorable_excursion),
            ("max_adverse_excursion", self.max_adverse_excursion),
        ):
            _decimal(value, field)
        if not (
            self.stop_loss_price < self.entry_price < self.take_profit_price
            or self.take_profit_price < self.entry_price < self.stop_loss_price
        ):
            raise ValueError("paper protection prices are invalid.")
        if self.max_favorable_excursion < 0 or self.max_adverse_excursion > 0:
            raise ValueError("MFE and MAE signs are invalid.")
        if len(self.quote_hash) != 64 or len(self.proposal_hash) != 64:
            raise ValueError("performance event hashes are required.")
        if self.event_type is not TmfPaperPerformanceEventType.MARK and not self.fill_hash:
            raise ValueError("entry and exit events require a fill hash.")
        _utc(self.observed_at, "observed_at")
        if (
            self.dry_run is not True
            or self.live_order_allowed
            or self.broker_connected
            or self.account_credentials_allowed
        ):
            raise ValueError("performance records are permanently paper-only.")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "event_type": self.event_type.value,
            "trade_id": self.trade_id,
            "instrument": self.instrument,
            "quantity": _decimal(self.quantity, "quantity", positive=True),
            "entry_price": _decimal(self.entry_price, "entry_price", positive=True),
            "current_price": _decimal(self.current_price, "current_price", positive=True),
            "stop_loss_price": _decimal(self.stop_loss_price, "stop_loss_price", positive=True),
            "take_profit_price": _decimal(
                self.take_profit_price,
                "take_profit_price",
                positive=True,
            ),
            "unrealized_pnl": _decimal(self.unrealized_pnl, "unrealized_pnl"),
            "realized_pnl": _decimal(self.realized_pnl, "realized_pnl"),
            "max_favorable_excursion": _decimal(
                self.max_favorable_excursion, "max_favorable_excursion"
            ),
            "max_adverse_excursion": _decimal(
                self.max_adverse_excursion, "max_adverse_excursion"
            ),
            "observed_at": _utc(self.observed_at, "observed_at"),
            "quote_hash": self.quote_hash,
            "proposal_hash": self.proposal_hash,
            "fill_hash": self.fill_hash,
            "previous_event_hash": self.previous_event_hash,
            "point_value": _decimal(self.point_value, "point_value", positive=True),
            "dry_run": True,
            "live_order_allowed": False,
            "broker_connected": False,
            "account_credentials_allowed": False,
        }

    @property
    def event_hash(self) -> str:
        return _hash(self.canonical_payload())

    @property
    def entry_side(self) -> PaperTradingSide:
        return (
            PaperTradingSide.BUY
            if self.stop_loss_price < self.entry_price
            else PaperTradingSide.SELL
        )


@dataclass(frozen=True, slots=True)
class TmfPaperSimulationJournal:
    instrument: str
    point_value: Decimal
    margin_requirement: TmfPaperMarginRequirement
    ledger: PaperTradingLedger
    events: tuple[TmfPaperPerformanceEvent, ...] = ()
    version: str = LIVE_TMF_PAPER_SIMULATION_VERSION

    def __post_init__(self) -> None:
        if not self.instrument or self.instrument != self.instrument.upper():
            raise ValueError("journal instrument must be canonical.")
        _decimal(self.point_value, "point_value", positive=True)
        if not isinstance(self.margin_requirement, TmfPaperMarginRequirement):
            raise TypeError("journal margin requirement is required.")
        if self.version != LIVE_TMF_PAPER_SIMULATION_VERSION:
            raise ValueError("unsupported live TMF paper journal version.")
        previous: str | None = None
        open_trade: str | None = None
        for event in self.events:
            if event.instrument != self.instrument or event.point_value != self.point_value:
                raise ValueError("journal event identity mismatch.")
            if event.previous_event_hash != previous:
                raise ValueError("journal event hash chain is invalid.")
            previous = event.event_hash
            if event.event_type is TmfPaperPerformanceEventType.ENTRY:
                if open_trade is not None:
                    raise ValueError("journal cannot contain overlapping paper positions.")
                open_trade = event.trade_id
            elif event.event_type in {
                TmfPaperPerformanceEventType.STOP_LOSS_EXIT,
                TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
            }:
                if open_trade != event.trade_id:
                    raise ValueError("journal exit does not match an open paper trade.")
                open_trade = None
        if bool(self.ledger.positions) != (open_trade is not None):
            raise ValueError("journal position and event state do not match.")

    @classmethod
    def empty(cls, config: TmfPaperSimulationConfig) -> TmfPaperSimulationJournal:
        return cls(
            config.instrument,
            config.point_value,
            config.margin_requirement,
            PaperTradingLedger(config.initial_cash),
        )

    @property
    def reserved_margin(self) -> Decimal:
        return sum(
            (
                abs(position.quantity) * self.margin_requirement.initial_margin
                for position in self.ledger.positions
            ),
            Decimal(0),
        )

    @property
    def required_maintenance_margin(self) -> Decimal:
        return sum(
            (
                abs(position.quantity) * self.margin_requirement.maintenance_margin
                for position in self.ledger.positions
            ),
            Decimal(0),
        )

    @property
    def unrealized_pnl(self) -> Decimal:
        entry = self.open_entry
        if entry is None:
            return Decimal(0)
        latest = self.last_event_for(entry.trade_id)
        return Decimal(0) if latest is None else latest.unrealized_pnl

    @property
    def account_equity(self) -> Decimal:
        return self.ledger.cash_balance + self.reserved_margin + self.unrealized_pnl

    @property
    def margin_status(self) -> TmfPaperMarginStatus:
        if not self.ledger.positions:
            return TmfPaperMarginStatus.NO_POSITION
        margin_equity = self.reserved_margin + self.unrealized_pnl
        if margin_equity <= self.required_maintenance_margin:
            return TmfPaperMarginStatus.MAINTENANCE_WARNING
        return TmfPaperMarginStatus.SAFE

    def margin_state_payload(self) -> dict[str, str]:
        return {
            "reserved_margin": _decimal(self.reserved_margin, "reserved_margin"),
            "required_maintenance_margin": _decimal(
                self.required_maintenance_margin,
                "required_maintenance_margin",
            ),
            "available_cash": _decimal(self.ledger.cash_balance, "available_cash"),
            "unrealized_pnl": _decimal(self.unrealized_pnl, "unrealized_pnl"),
            "account_equity": _decimal(self.account_equity, "account_equity"),
            "status": self.margin_status.value,
        }

    def performance_summary_payload(self) -> dict[str, object]:
        """Summarize closed paper trades without changing any entry rule."""
        exits = [
            event
            for event in self.events
            if event.event_type
            in {
                TmfPaperPerformanceEventType.STOP_LOSS_EXIT,
                TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
            }
        ]
        outcomes = [event.realized_pnl for event in exits]
        wins = [value for value in outcomes if value > 0]
        losses = [value for value in outcomes if value < 0]
        breakeven = [value for value in outcomes if value == 0]
        net = sum(outcomes, Decimal(0))
        gross_profit = sum(wins, Decimal(0))
        gross_loss = abs(sum(losses, Decimal(0)))
        cumulative = Decimal(0)
        peak = Decimal(0)
        maximum_drawdown = Decimal(0)
        for value in outcomes:
            cumulative += value
            peak = max(peak, cumulative)
            maximum_drawdown = max(maximum_drawdown, peak - cumulative)

        def direction_summary(side: PaperTradingSide) -> dict[str, object]:
            selected = [event.realized_pnl for event in exits if event.entry_side is side]
            selected_wins = sum(1 for value in selected if value > 0)
            return {
                "sample_size": len(selected),
                "wins": selected_wins,
                "win_rate": (
                    None
                    if not selected
                    else str(
                        (Decimal(selected_wins) / Decimal(len(selected)) * Decimal(100)).quantize(
                            Decimal("0.01")
                        )
                    )
                ),
                "net_pnl": str(sum(selected, Decimal(0))),
            }

        sample_size = len(outcomes)
        return {
            "sample_size": sample_size,
            "minimum_sample_size": MINIMUM_PERFORMANCE_SAMPLE_SIZE,
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(breakeven),
            "win_rate": (
                None
                if not outcomes
                else str(
                    (Decimal(len(wins)) / Decimal(sample_size) * Decimal(100)).quantize(
                        Decimal("0.01")
                    )
                )
            ),
            "net_pnl": str(net),
            "expectancy": None if not outcomes else str((net / Decimal(sample_size)).quantize(Decimal("0.01"))),
            "gross_profit": str(gross_profit),
            "gross_loss": str(gross_loss),
            "profit_factor": (
                None
                if gross_loss == 0
                else str((gross_profit / gross_loss).quantize(Decimal("0.01")))
            ),
            "maximum_drawdown": str(maximum_drawdown),
            "long": direction_summary(PaperTradingSide.BUY),
            "short": direction_summary(PaperTradingSide.SELL),
            "adjustment_allowed": sample_size >= MINIMUM_PERFORMANCE_SAMPLE_SIZE,
            "live_order_allowed": False,
        }

    def canonical_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "instrument": self.instrument,
            "point_value": _decimal(self.point_value, "point_value", positive=True),
            "margin_requirement": self.margin_requirement.canonical_payload(),
            "margin_state": self.margin_state_payload(),
            "ledger": self.ledger.canonical_payload(),
            "ledger_hash": self.ledger.ledger_hash,
            "events": [event.canonical_payload() for event in self.events],
        }

    @property
    def journal_hash(self) -> str:
        return _hash(self.canonical_payload())

    @property
    def open_entry(self) -> TmfPaperPerformanceEvent | None:
        entry: TmfPaperPerformanceEvent | None = None
        for event in self.events:
            if event.event_type is TmfPaperPerformanceEventType.ENTRY:
                entry = event
            elif event.event_type in {
                TmfPaperPerformanceEventType.STOP_LOSS_EXIT,
                TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
            }:
                entry = None
        return entry

    def last_event_for(self, trade_id: str) -> TmfPaperPerformanceEvent | None:
        return next((item for item in reversed(self.events) if item.trade_id == trade_id), None)

    def with_event(
        self,
        event: TmfPaperPerformanceEvent,
        ledger: PaperTradingLedger,
    ) -> TmfPaperSimulationJournal:
        return TmfPaperSimulationJournal(
            self.instrument,
            self.point_value,
            self.margin_requirement,
            ledger,
            (*self.events, event),
            self.version,
        )


class TmfPaperJournalStore:
    """Atomic local JSON journal; it stores no provider payload or credentials."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save(self, journal: TmfPaperSimulationJournal) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": LIVE_TMF_PAPER_JOURNAL_SCHEMA,
            **journal.canonical_payload(),
            "journal_hash": journal.journal_hash,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        replace(temporary, self.path)

    def load(self, config: TmfPaperSimulationConfig) -> TmfPaperSimulationJournal:
        if not self.path.is_file():
            return TmfPaperSimulationJournal.empty(config)
        try:
            payload = cast(
                dict[str, Any],
                loads(self.path.read_text(encoding="utf-8")),
            )
            if payload.get("schema") == LEGACY_TMF_PAPER_JOURNAL_SCHEMA:
                return self._migrate_legacy_empty_journal(payload, config)
            if (
                payload["schema"] != LIVE_TMF_PAPER_JOURNAL_SCHEMA
                or payload["version"] != LIVE_TMF_PAPER_SIMULATION_VERSION
                or payload["instrument"] != config.instrument
                or Decimal(payload["point_value"]) != config.point_value
            ):
                raise ValueError("PAPER_JOURNAL_IDENTITY_MISMATCH")
            margin_requirement = self._margin_from_payload(
                payload["margin_requirement"]
            )
            if margin_requirement != config.margin_requirement:
                raise ValueError("PAPER_JOURNAL_MARGIN_IDENTITY_MISMATCH")
            ledger = self._ledger_from_payload(payload["ledger"])
            if ledger.ledger_hash != payload["ledger_hash"]:
                raise ValueError("PAPER_JOURNAL_LEDGER_HASH_MISMATCH")
            events = tuple(self._event_from_payload(item) for item in payload["events"])
            journal = TmfPaperSimulationJournal(
                config.instrument,
                config.point_value,
                margin_requirement,
                ledger,
                events,
            )
            if journal.journal_hash != payload["journal_hash"]:
                raise ValueError("PAPER_JOURNAL_HASH_MISMATCH")
            return journal
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise ValueError("PAPER_JOURNAL_INVALID") from error

    @staticmethod
    def _margin_from_payload(item: dict[str, Any]) -> TmfPaperMarginRequirement:
        return TmfPaperMarginRequirement(
            Decimal(str(item["initial_margin"])),
            Decimal(str(item["maintenance_margin"])),
            _parse_utc(item["effective_at"], "margin.effective_at"),
            str(item["source"]),
        )

    @staticmethod
    def _ledger_from_payload(ledger_payload: dict[str, Any]) -> PaperTradingLedger:
        positions = tuple(
            PaperTradingPosition(
                item["instrument"],
                Decimal(item["quantity"]),
                Decimal(item["average_price"]),
                Decimal(item["realized_pnl"]),
                _parse_utc(item["updated_at"], "position.updated_at"),
            )
            for item in ledger_payload["positions"]
        )
        cash_entries = tuple(
            PaperTradingCashLedgerEntry(
                item["entry_id"],
                item["fill_id"],
                Decimal(item["cash_delta"]),
                Decimal(item["fees"]),
                Decimal(item["balance_after"]),
            )
            for item in ledger_payload["cash_entries"]
        )
        return PaperTradingLedger(
            Decimal(ledger_payload["cash_balance"]),
            positions,
            cash_entries,
            tuple(ledger_payload["used_idempotency_keys"]),
            bool(ledger_payload["allow_negative_cash"]),
            bool(ledger_payload["allow_short"]),
        )

    def _migrate_legacy_empty_journal(
        self,
        payload: dict[str, Any],
        config: TmfPaperSimulationConfig,
    ) -> TmfPaperSimulationJournal:
        if (
            payload["version"] != LEGACY_TMF_PAPER_SIMULATION_VERSION
            or payload["instrument"] != config.instrument
            or Decimal(payload["point_value"]) != config.point_value
        ):
            raise ValueError("PAPER_JOURNAL_LEGACY_IDENTITY_MISMATCH")
        ledger = self._ledger_from_payload(payload["ledger"])
        if ledger.ledger_hash != payload["ledger_hash"]:
            raise ValueError("PAPER_JOURNAL_LEGACY_LEDGER_HASH_MISMATCH")
        if (
            payload["events"]
            or ledger.positions
            or ledger.cash_entries
            or ledger.used_idempotency_keys
        ):
            raise ValueError("PAPER_JOURNAL_LEGACY_TRADES_REQUIRE_ARCHIVE")
        legacy_canonical = {
            "version": LEGACY_TMF_PAPER_SIMULATION_VERSION,
            "instrument": config.instrument,
            "point_value": _decimal(config.point_value, "point_value", positive=True),
            "ledger": ledger.canonical_payload(),
            "ledger_hash": ledger.ledger_hash,
            "events": [],
        }
        if _hash(legacy_canonical) != payload["journal_hash"]:
            raise ValueError("PAPER_JOURNAL_LEGACY_HASH_MISMATCH")
        return TmfPaperSimulationJournal(
            config.instrument,
            config.point_value,
            config.margin_requirement,
            ledger,
        )

    @staticmethod
    def _event_from_payload(item: dict[str, object]) -> TmfPaperPerformanceEvent:
        return TmfPaperPerformanceEvent(
            TmfPaperPerformanceEventType(str(item["event_type"])),
            str(item["trade_id"]),
            str(item["instrument"]),
            Decimal(str(item["quantity"])),
            Decimal(str(item["entry_price"])),
            Decimal(str(item["current_price"])),
            Decimal(str(item["stop_loss_price"])),
            Decimal(str(item["take_profit_price"])),
            Decimal(str(item["unrealized_pnl"])),
            Decimal(str(item["realized_pnl"])),
            Decimal(str(item["max_favorable_excursion"])),
            Decimal(str(item["max_adverse_excursion"])),
            _parse_utc(item["observed_at"], "event.observed_at"),
            str(item["quote_hash"]),
            str(item["proposal_hash"]),
            None if item["fill_hash"] is None else str(item["fill_hash"]),
            None
            if item["previous_event_hash"] is None
            else str(item["previous_event_hash"]),
            Decimal(str(item["point_value"])),
        )


@dataclass(frozen=True, slots=True)
class TmfPaperCycleResult:
    action: TmfPaperCycleAction
    direction: str
    quote_hash: str | None
    proposal_hash: str | None
    fill_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    journal: TmfPaperSimulationJournal
    performance_event: TmfPaperPerformanceEvent | None = None
    dry_run: bool = True
    live_order_allowed: bool = False
    broker_connected: bool = False
    account_credentials_allowed: bool = False

    def __post_init__(self) -> None:
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("cycle reason codes must be canonical.")
        if self.fill_hashes != tuple(sorted(self.fill_hashes)):
            raise ValueError("cycle fill hashes must be canonical.")
        if (
            self.dry_run is not True
            or self.live_order_allowed
            or self.broker_connected
            or self.account_credentials_allowed
        ):
            raise ValueError("cycle result is permanently paper-only.")

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action": self.action.value,
            "direction": self.direction,
            "quote_hash": self.quote_hash,
            "proposal_hash": self.proposal_hash,
            "fill_hashes": list(self.fill_hashes),
            "reason_codes": list(self.reason_codes),
            "journal_hash": self.journal.journal_hash,
            "cash_balance": str(self.journal.ledger.cash_balance),
            "margin_requirement": self.journal.margin_requirement.canonical_payload(),
            "margin_state": self.journal.margin_state_payload(),
            "performance_summary": self.journal.performance_summary_payload(),
            "open_positions": len(self.journal.ledger.positions),
            "performance_event": (
                None
                if self.performance_event is None
                else self.performance_event.canonical_payload()
            ),
            "dry_run": True,
            "live_order_allowed": False,
            "broker_connected": False,
            "account_credentials_allowed": False,
            "execution_boundary": {
                "mode": "paper_only",
                "automatic_paper_execution": True,
                "real_order_requires_human_action": True,
                "broker_submission_available": False,
                "live_order_allowed": False,
            },
        }
        payload["audit_hash"] = _hash(payload)
        return payload


class LiveTmfPaperSimulation:
    """Stateful paper session with one-contract risk, idempotency and journaling."""

    def __init__(
        self,
        config: TmfPaperSimulationConfig,
        *,
        journal: TmfPaperSimulationJournal | None = None,
        store: TmfPaperJournalStore | None = None,
    ) -> None:
        if not isinstance(config, TmfPaperSimulationConfig):
            raise TypeError("TmfPaperSimulationConfig is required.")
        self.config = config
        self.store = store
        self.journal = journal or TmfPaperSimulationJournal.empty(config)
        self._pending_entry_direction: str | None = None
        self._pending_entry_candles: list[tuple[datetime, Decimal]] = []
        if (
            self.journal.instrument != config.instrument
            or self.journal.point_value != config.point_value
            or self.journal.margin_requirement != config.margin_requirement
        ):
            raise ValueError("paper journal does not match the simulation config.")

    def process_candles(
        self,
        value: CompleteFiveTimeframeCandleResult | FiveTimeframeCandleResult,
        *,
        evaluated_at: datetime,
    ) -> TmfPaperCycleResult:
        """Evaluate KAM naturally, then pass only its canonical paper direction."""
        preview = build_verified_five_timeframe_analysis_preview(
            value,
            evaluated_at=evaluated_at,
        )
        quote = build_tmf_paper_quote(value, instrument=self.config.instrument)
        return self.process_evaluation(preview.paper_direction, quote, evaluated_at=evaluated_at)

    def process_evaluation(
        self,
        direction: FiveTimeframePaperDirection,
        quote: TmfPaperQuote,
        *,
        evaluated_at: datetime,
    ) -> TmfPaperCycleResult:
        """Apply a canonical direction to a verified quote; no signal is overridden."""
        if not isinstance(direction, FiveTimeframePaperDirection):
            raise TypeError("FiveTimeframePaperDirection is required.")
        if not isinstance(quote, TmfPaperQuote):
            raise TypeError("TmfPaperQuote is required.")
        _utc(evaluated_at, "evaluated_at")
        if quote.instrument != self.config.instrument:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("QUOTE_INSTRUMENT_MISMATCH",),
            )
        age_seconds = (evaluated_at - quote.observed_at).total_seconds()
        if age_seconds < 0:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("QUOTE_FROM_FUTURE",),
            )
        if age_seconds > self.config.max_quote_age_seconds:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("QUOTE_STALE",),
            )
        if quote.price % self.config.tick_size != 0:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("QUOTE_NOT_ON_TICK",),
            )
        if self.journal.open_entry is not None:
            return self._mark_or_exit(direction, quote, evaluated_at)
        entry_side = {
            ("LONG", "PAPER_BUY"): PaperTradingSide.BUY,
            ("SHORT", "PAPER_SELL"): PaperTradingSide.SELL,
        }.get((direction.direction, direction.action))
        if entry_side is None:
            self._reset_entry_confirmation()
            return self._result(
                TmfPaperCycleAction.HOLD,
                direction.direction,
                quote,
                reasons=("KAM_ENTRY_CONDITION_NOT_MET",),
            )

        if self.config.entry_confirmation_candles > 1:
            if self._pending_entry_direction != direction.direction:
                self._pending_entry_direction = direction.direction
                self._pending_entry_candles = []
            if (
                not self._pending_entry_candles
                or quote.observed_at > self._pending_entry_candles[-1][0]
            ):
                if self._pending_entry_candles:
                    previous_price = self._pending_entry_candles[-1][1]
                    continued = (
                        direction.direction == "LONG" and quote.price > previous_price
                    ) or (
                        direction.direction == "SHORT" and quote.price < previous_price
                    )
                    if not continued:
                        self._pending_entry_candles = [(quote.observed_at, quote.price)]
                        return self._result(
                            TmfPaperCycleAction.HOLD,
                            direction.direction,
                            quote,
                            reasons=("ENTRY_PRICE_CONFIRMATION_PENDING",),
                        )
                    if (
                        abs(quote.price - previous_price)
                        > self.config.max_entry_confirmation_move_points
                    ):
                        self._pending_entry_candles = [(quote.observed_at, quote.price)]
                        return self._result(
                            TmfPaperCycleAction.HOLD,
                            direction.direction,
                            quote,
                            reasons=("ENTRY_CONFIRMATION_MOVE_TOO_LARGE",),
                        )
                self._pending_entry_candles.append((quote.observed_at, quote.price))
            if len(self._pending_entry_candles) < self.config.entry_confirmation_candles:
                return self._result(
                    TmfPaperCycleAction.HOLD,
                    direction.direction,
                    quote,
                    reasons=("ENTRY_CONFIRMATION_PENDING",),
                )

        last_exit = next(
            (
                event
                for event in reversed(self.journal.events)
                if event.event_type
                in {
                    TmfPaperPerformanceEventType.STOP_LOSS_EXIT,
                    TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
                }
            ),
            None,
        )
        if last_exit is not None and evaluated_at < (
            last_exit.observed_at
            + timedelta(minutes=self.config.reentry_cooldown_minutes)
        ):
            return self._result(
                TmfPaperCycleAction.HOLD,
                direction.direction,
                quote,
                reasons=("REENTRY_COOLDOWN_ACTIVE",),
            )

        current_risk_day = _taiwan_risk_day(evaluated_at)
        entries_today = sum(
            1
            for event in self.journal.events
            if event.event_type is TmfPaperPerformanceEventType.ENTRY
            and _taiwan_risk_day(event.observed_at) == current_risk_day
        )
        if entries_today >= self.config.max_entries_per_risk_day:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("MAX_DAILY_ENTRIES_EXCEEDED",),
            )

        proposal = build_paper_order_proposal(
            self._proposal_input(direction, quote, evaluated_at, entry_side)
        ).proposal
        if proposal is None:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                reasons=("PROPOSAL_BUILD_FAILED",),
            )
        if not self.config.paper_trading_enabled:
            return self._result(
                TmfPaperCycleAction.PENDING_MANUAL_CONFIRMATION,
                direction.direction,
                quote,
                proposal_hash=proposal.proposal_hash,
                reasons=("PAPER_TRADING_NOT_ARMED",),
            )
        if not self.config.manual_approval_granted:
            return self._result(
                TmfPaperCycleAction.PENDING_MANUAL_CONFIRMATION,
                direction.direction,
                quote,
                proposal_hash=proposal.proposal_hash,
                reasons=("MANUAL_CONFIRMATION_REQUIRED",),
            )

        required_initial_margin = self.config.initial_margin * self.config.quantity
        if self.journal.ledger.cash_balance < required_initial_margin:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                proposal_hash=proposal.proposal_hash,
                reasons=("INSUFFICIENT_INITIAL_MARGIN",),
            )

        safety = self._safety(evaluated_at)
        runner = PaperOrderProposalRunnerState(self.journal.ledger.used_idempotency_keys)
        confirmation, request, _ = confirm_paper_order_proposal(
            proposal,
            runner,
            safety,
            evaluated_at,
            manual_confirmed=True,
        )
        if request is None:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                proposal_hash=proposal.proposal_hash,
                reasons=confirmation.reason_codes,
            )
        matched = match_paper_trading_order(
            request,
            PaperTradingOrderType.MARKET,
            self._book(quote),
            self._matching_ledger(quote),
            safety,
        )
        if matched.state is not PaperTradingMatchState.FILLED or not matched.fills:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                proposal_hash=proposal.proposal_hash,
                reasons=matched.reason_codes or ("PAPER_FILL_NOT_COMPLETED",),
            )
        fill = matched.fills[0]
        stop = quote.price + (
            -self.config.stop_loss_points
            if entry_side is PaperTradingSide.BUY
            else self.config.stop_loss_points
        )
        take = quote.price + (
            self.config.take_profit_points
            if entry_side is PaperTradingSide.BUY
            else -self.config.take_profit_points
        )
        event = TmfPaperPerformanceEvent(
            TmfPaperPerformanceEventType.ENTRY,
            request.idempotency_key,
            self.config.instrument,
            fill.quantity,
            fill.price,
            fill.price,
            stop,
            take,
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            quote.observed_at,
            quote.quote_hash,
            proposal.proposal_hash,
            fill.fill_hash,
            self.journal.events[-1].event_hash if self.journal.events else None,
            self.config.point_value,
        )
        margin_ledger = self._reserve_margin(matched.ledger, fill)
        self._publish(self.journal.with_event(event, margin_ledger))
        self._reset_entry_confirmation()
        return self._result(
            TmfPaperCycleAction.ENTRY_FILLED,
            direction.direction,
            quote,
            proposal_hash=proposal.proposal_hash,
            fills=(fill.fill_hash,),
            event=event,
        )

    def _reset_entry_confirmation(self) -> None:
        self._pending_entry_direction = None
        self._pending_entry_candles = []

    def _matching_ledger(self, quote: TmfPaperQuote) -> PaperTradingLedger:
        """Give the generic matcher enough synthetic cash; final cash uses futures margin."""
        required_notional = quote.price * self.config.quantity
        source = self.journal.ledger
        return PaperTradingLedger(
            cash_balance=max(source.cash_balance, required_notional),
            positions=source.positions,
            cash_entries=source.cash_entries,
            used_idempotency_keys=source.used_idempotency_keys,
            allow_negative_cash=False,
            allow_short=True,
        )

    def _reserve_margin(
        self,
        matched_ledger: PaperTradingLedger,
        fill: PaperTradingFill,
    ) -> PaperTradingLedger:
        required = self.config.initial_margin * fill.quantity
        debit = required + fill.fees
        balance = self.journal.ledger.cash_balance - debit
        entry = PaperTradingCashLedgerEntry(
            fill.fill_id,
            fill.fill_id,
            -debit,
            fill.fees,
            balance,
        )
        return PaperTradingLedger(
            cash_balance=balance,
            positions=matched_ledger.positions,
            cash_entries=(*self.journal.ledger.cash_entries, entry),
            used_idempotency_keys=matched_ledger.used_idempotency_keys,
            allow_negative_cash=False,
            allow_short=True,
        )

    def _proposal_input(
        self,
        direction: FiveTimeframePaperDirection,
        quote: TmfPaperQuote,
        evaluated_at: datetime,
        entry_side: PaperTradingSide,
    ) -> PaperOrderProposalInput:
        source_hash = _hash(
            {
                "direction": direction.safe_payload(),
                "quote_hash": quote.quote_hash,
                "simulation_version": LIVE_TMF_PAPER_SIMULATION_VERSION,
            }
        )
        return PaperOrderProposalInput(
            source_hash[:32],
            "kam-five-timeframe-paper-v1",
            self.config.instrument,
            (
                PaperOrderProposalAction.BUY
                if entry_side is PaperTradingSide.BUY
                else PaperOrderProposalAction.SELL
            ),
            PaperOrderProposalOrderType.MARKET,
            self.config.quantity,
            quote.price,
            None,
            quote.price + (
                -self.config.stop_loss_points
                if entry_side is PaperTradingSide.BUY
                else self.config.stop_loss_points
            ),
            quote.price + (
                self.config.take_profit_points
                if entry_side is PaperTradingSide.BUY
                else -self.config.take_profit_points
            ),
            Decimal(1),
            PaperOrderProposalRisk(
                PaperOrderProposalRiskStatus.ACCEPTABLE,
                "五週期完整一致；僅建立 TMF 雙向模擬交易並保留官方原始保證金。",
            ),
            (
                PaperOrderProposalReason(
                    direction.reason_code,
                    "KAM 五週期自然出現雙向模擬條件。",
                ),
            ),
            evaluated_at,
            evaluated_at + timedelta(minutes=5),
            source_hash,
        )

    def _safety(self, evaluated_at: datetime) -> PaperTradingSafetyState:
        current_risk_day = _taiwan_risk_day(evaluated_at)
        realized = sum(
            (
                event.realized_pnl
                for event in self.journal.events
                if event.event_type
                in {
                    TmfPaperPerformanceEventType.STOP_LOSS_EXIT,
                    TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT,
                }
                and _taiwan_risk_day(event.observed_at) == current_risk_day
            ),
            Decimal(0),
        )
        account = PaperTradingAccountSnapshot(
            self.journal.ledger.positions,
            realized,
            evaluated_at,
        )
        limits = PaperTradingRiskLimits(
            Decimal(1),
            self.config.max_order_notional,
            self.config.max_daily_loss,
            1,
            (self.config.instrument,),
            (0, 1, 2, 3, 4, 5, 6),
            time(0, 0),
            time(23, 59, 59, 999999),
        )
        armed = self.config.paper_trading_enabled and self.config.manual_approval_granted
        return PaperTradingSafetyState(
            paper_trading_enabled=armed,
            emergency_stop=not armed,
            used_idempotency_keys=self.journal.ledger.used_idempotency_keys,
            account_snapshot=account,
            risk_limits=limits,
        )

    def _book(self, quote: TmfPaperQuote) -> InMemoryPaperOrderBook:
        return InMemoryPaperOrderBook(
            (
                OfflineMarketSnapshot(
                    quote.instrument,
                    quote.price,
                    quote.price,
                    self.config.quantity,
                    self.config.quantity,
                    quote.observed_at,
                ),
            )
        )

    def _mark_or_exit(
        self,
        direction: FiveTimeframePaperDirection,
        quote: TmfPaperQuote,
        evaluated_at: datetime,
    ) -> TmfPaperCycleResult:
        entry = self.journal.open_entry
        if entry is None:
            raise RuntimeError("open paper entry disappeared.")
        previous = self.journal.last_event_for(entry.trade_id)
        if previous is None:
            raise RuntimeError("paper performance chain is incomplete.")
        if previous.quote_hash == quote.quote_hash:
            return self._result(
                TmfPaperCycleAction.DUPLICATE_IGNORED,
                direction.direction,
                quote,
                proposal_hash=entry.proposal_hash,
                reasons=("QUOTE_ALREADY_RECORDED",),
            )
        if quote.observed_at <= previous.observed_at:
            return self._result(
                TmfPaperCycleAction.REJECTED,
                direction.direction,
                quote,
                proposal_hash=entry.proposal_hash,
                reasons=("OUT_OF_ORDER_QUOTE",),
            )
        direction_multiplier = (
            Decimal(1) if entry.entry_side is PaperTradingSide.BUY else Decimal(-1)
        )
        pnl = (
            (quote.price - entry.entry_price)
            * direction_multiplier
            * entry.quantity
            * self.config.point_value
        )
        mfe = max(previous.max_favorable_excursion, pnl, Decimal(0))
        mae = min(previous.max_adverse_excursion, pnl, Decimal(0))
        stop_loss_price = previous.stop_loss_price
        take_profit_price = previous.take_profit_price
        trend_still_aligned = (
            entry.entry_side is PaperTradingSide.BUY
            and direction.direction == "LONG"
            and direction.action == "PAPER_BUY"
            and direction.eligible
        ) or (
            entry.entry_side is PaperTradingSide.SELL
            and direction.direction == "SHORT"
            and direction.action == "PAPER_SELL"
            and direction.eligible
        )
        take_profit_reached = (
            entry.entry_side is PaperTradingSide.BUY
            and quote.price >= take_profit_price
        ) or (
            entry.entry_side is PaperTradingSide.SELL
            and quote.price <= take_profit_price
        )
        trend_hold_extended = (
            self.config.trend_hold_enabled
            and trend_still_aligned
            and take_profit_reached
        )
        if trend_hold_extended:
            if entry.entry_side is PaperTradingSide.BUY:
                extension_count = (
                    (quote.price - take_profit_price)
                    // self.config.take_profit_extension_points
                ) + 1
                take_profit_price += (
                    self.config.take_profit_extension_points * extension_count
                )
                stop_loss_price = max(
                    stop_loss_price,
                    entry.entry_price - self.config.tick_size,
                )
            else:
                extension_count = (
                    (take_profit_price - quote.price)
                    // self.config.take_profit_extension_points
                ) + 1
                take_profit_price -= (
                    self.config.take_profit_extension_points * extension_count
                )
                stop_loss_price = min(
                    stop_loss_price,
                    entry.entry_price + self.config.tick_size,
                )
        exit_type: TmfPaperPerformanceEventType | None = None
        if entry.entry_side is PaperTradingSide.BUY and quote.price <= stop_loss_price:
            exit_type = TmfPaperPerformanceEventType.STOP_LOSS_EXIT
        elif (
            entry.entry_side is PaperTradingSide.BUY
            and quote.price >= take_profit_price
            and not trend_hold_extended
        ):
            exit_type = TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT
        elif entry.entry_side is PaperTradingSide.SELL and quote.price >= stop_loss_price:
            exit_type = TmfPaperPerformanceEventType.STOP_LOSS_EXIT
        elif (
            entry.entry_side is PaperTradingSide.SELL
            and quote.price <= take_profit_price
            and not trend_hold_extended
        ):
            exit_type = TmfPaperPerformanceEventType.TAKE_PROFIT_EXIT

        fill_hash: str | None = None
        ledger = self.journal.ledger
        action = TmfPaperCycleAction.POSITION_MARKED
        if exit_type is not None:
            request = PaperTradingOrderRequest(
                _hash(
                    {
                        "trade_id": entry.trade_id,
                        "exit_quote": quote.quote_hash,
                        "exit_type": exit_type.value,
                    }
                )[:32],
                self.config.instrument,
                (
                    PaperTradingSide.SELL
                    if entry.entry_side is PaperTradingSide.BUY
                    else PaperTradingSide.BUY
                ),
                entry.quantity,
                quote.price,
                evaluated_at,
            )
            matched = match_paper_trading_order(
                request,
                PaperTradingOrderType.MARKET,
                self._book(quote),
                self._matching_ledger(quote),
                self._safety(evaluated_at),
            )
            if matched.state is not PaperTradingMatchState.FILLED or not matched.fills:
                return self._result(
                    TmfPaperCycleAction.REJECTED,
                    direction.direction,
                    quote,
                    proposal_hash=entry.proposal_hash,
                    reasons=matched.reason_codes or ("PAPER_EXIT_NOT_COMPLETED",),
                )
            fill = matched.fills[0]
            fill_hash = fill.fill_hash
            ledger = self._release_margin(matched.ledger, fill, pnl)
            action = TmfPaperCycleAction.EXIT_FILLED

        event = TmfPaperPerformanceEvent(
            exit_type or TmfPaperPerformanceEventType.MARK,
            entry.trade_id,
            entry.instrument,
            entry.quantity,
            entry.entry_price,
            quote.price,
            stop_loss_price,
            take_profit_price,
            Decimal(0) if exit_type is not None else pnl,
            pnl if exit_type is not None else Decimal(0),
            mfe,
            mae,
            quote.observed_at,
            quote.quote_hash,
            entry.proposal_hash,
            fill_hash,
            self.journal.events[-1].event_hash,
            self.config.point_value,
        )
        self._publish(self.journal.with_event(event, ledger))
        reasons = (
            ("TREND_HOLD_TAKE_PROFIT_EXTENDED",)
            if trend_hold_extended
            else ("MARGIN_MAINTENANCE_WARNING",)
            if exit_type is None
            and self.journal.margin_status is TmfPaperMarginStatus.MAINTENANCE_WARNING
            else ()
        )
        return self._result(
            action,
            direction.direction,
            quote,
            proposal_hash=entry.proposal_hash,
            fills=() if fill_hash is None else (fill_hash,),
            reasons=reasons,
            event=event,
        )

    def _release_margin(
        self,
        matched_ledger: PaperTradingLedger,
        fill: PaperTradingFill,
        realized_pnl: Decimal,
    ) -> PaperTradingLedger:
        release = self.config.initial_margin * fill.quantity + realized_pnl - fill.fees
        balance = self.journal.ledger.cash_balance + release
        entry = PaperTradingCashLedgerEntry(
            fill.fill_id,
            fill.fill_id,
            release,
            fill.fees,
            balance,
        )
        return PaperTradingLedger(
            cash_balance=balance,
            positions=matched_ledger.positions,
            cash_entries=(*self.journal.ledger.cash_entries, entry),
            used_idempotency_keys=matched_ledger.used_idempotency_keys,
            allow_negative_cash=False,
            allow_short=True,
        )

    def _publish(self, journal: TmfPaperSimulationJournal) -> None:
        if self.store is not None:
            self.store.save(journal)
        self.journal = journal

    def _result(
        self,
        action: TmfPaperCycleAction,
        direction: str,
        quote: TmfPaperQuote | None,
        *,
        proposal_hash: str | None = None,
        fills: tuple[str, ...] = (),
        reasons: tuple[str, ...] = (),
        event: TmfPaperPerformanceEvent | None = None,
    ) -> TmfPaperCycleResult:
        return TmfPaperCycleResult(
            action,
            direction,
            None if quote is None else quote.quote_hash,
            proposal_hash,
            tuple(sorted(fills)),
            tuple(sorted(set(reasons))),
            self.journal,
            event,
        )


__all__ = [
    "LEGACY_TMF_PAPER_JOURNAL_SCHEMA",
    "LEGACY_TMF_PAPER_SIMULATION_VERSION",
    "LIVE_TMF_PAPER_JOURNAL_SCHEMA",
    "LIVE_TMF_PAPER_SIMULATION_VERSION",
    "LiveTmfPaperSimulation",
    "TmfPaperCycleAction",
    "TmfPaperCycleResult",
    "TmfPaperJournalStore",
    "TmfPaperMarginRequirement",
    "TmfPaperMarginStatus",
    "TmfPaperPerformanceEvent",
    "TmfPaperPerformanceEventType",
    "TmfPaperQuote",
    "TmfPaperSimulationConfig",
    "TmfPaperSimulationJournal",
    "build_tmf_paper_quote",
]
