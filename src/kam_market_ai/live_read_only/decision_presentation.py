"""Deterministic, read-only presentation mapping for selected market snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from .market_snapshot import (
    MarketDataFreshness,
    MarketDataSource,
    MarketSnapshot,
    MarketSnapshotStatus,
    TradingSession,
)


@dataclass(frozen=True, slots=True)
class DirectionPresentation:
    label: str
    state: str
    reason: str


@dataclass(frozen=True, slots=True)
class ControlPresentation:
    label: str
    bull_score: int | None
    bear_score: int | None


@dataclass(frozen=True, slots=True)
class CyclePresentation:
    label: str
    state: str


@dataclass(frozen=True, slots=True)
class TimeframePresentation:
    timeframe: str
    label: str


@dataclass(frozen=True, slots=True)
class TrendHealthPresentation:
    label: str


@dataclass(frozen=True, slots=True)
class NextStepPresentation:
    label: str
    state: str


@dataclass(frozen=True, slots=True)
class DecisionPresentation:
    product_code: str
    contract_code: str | None
    direction: DirectionPresentation
    control: ControlPresentation
    cycle: CyclePresentation
    timeframes: tuple[TimeframePresentation, ...]
    trend_health: TrendHealthPresentation
    next_step: NextStepPresentation


class SelectedSnapshotDecisionPresenter:
    """Offline display mapping, not a strategy, signal, or proposal engine."""

    def present(
        self, snapshot: MarketSnapshot, demo_payload: object = None, safety_status: object = None
    ) -> DecisionPresentation:
        safe = (
            snapshot.status is MarketSnapshotStatus.READY
            and snapshot.freshness is MarketDataFreshness.FRESH
            and snapshot.trading_session is not TradingSession.CLOSED
            and snapshot.market_status != "HALTED"
        )
        if snapshot.status in {
            MarketSnapshotStatus.INVALID_PRODUCT,
            MarketSnapshotStatus.INVALID_CONTRACT,
            MarketSnapshotStatus.INVALID_TIMESTAMP,
            MarketSnapshotStatus.CLIENT_UNAVAILABLE,
            MarketSnapshotStatus.TIMEOUT,
            MarketSnapshotStatus.MALFORMED_PAYLOAD,
        }:
            return DecisionPresentation(
                snapshot.product_code,
                snapshot.contract_code,
                DirectionPresentation("資料不足／無法判讀", "invalid", "資料不足／無法判讀"),
                ControlPresentation("不可判讀", None, None),
                CyclePresentation("不可判讀", "invalid"),
                tuple(
                    TimeframePresentation(name, "等待資料")
                    for name in ("週線", "日線", "60 分", "15 分", "5 分")
                ),
                TrendHealthPresentation("資料不足"),
                NextStepPresentation("等待資料恢復", "invalid"),
            )
        if not safe:
            if snapshot.trading_session is TradingSession.CLOSED:
                text, next_text, state = "休市／不可判讀", "等待市場恢復", "closed"
            elif snapshot.market_status == "HALTED":
                text, next_text, state = "暫停／不可判讀", "等待資料恢復", "halted"
            else:
                text, next_text, state = "資料不足／無法判讀", "等待資料恢復", "invalid"
            return DecisionPresentation(
                snapshot.product_code,
                snapshot.contract_code,
                DirectionPresentation(text, state, "離線快照不可用於交易推論"),
                ControlPresentation("不可判讀", None, None),
                CyclePresentation("不可判讀", state),
                tuple(
                    TimeframePresentation(name, "等待／資料不足")
                    for name in ("週線", "日線", "60 分", "15 分", "5 分")
                ),
                TrendHealthPresentation("資料不足／無法判讀"),
                NextStepPresentation(next_text, state),
            )
        if snapshot.data_source is MarketDataSource.FUTURE_LIVE:
            return DecisionPresentation(
                snapshot.product_code,
                snapshot.contract_code,
                DirectionPresentation(
                    "尚未判定",
                    "live-data-only",
                    "真實行情已連線；四週期決策資料尚未接入",
                ),
                ControlPresentation("不可判讀", None, None),
                CyclePresentation("等待四週期資料", "live-data-only"),
                tuple(
                    TimeframePresentation(name, "等待 K 線")
                    for name in ("週線", "日線", "60 分", "15 分", "5 分")
                ),
                TrendHealthPresentation("資料建置中"),
                NextStepPresentation("保持觀察", "live-data-only"),
            )
        return DecisionPresentation(
            snapshot.product_code,
            snapshot.contract_code,
            DirectionPresentation("偏多", "active", "離線展示：日盤交易中"),
            ControlPresentation("多方控制", 6, 4),
            CyclePresentation("多方延伸", "healthy"),
            tuple(
                TimeframePresentation(name, "多方健康")
                for name in ("週線", "日線", "60 分", "15 分", "5 分")
            ),
            TrendHealthPresentation("健康"),
            NextStepPresentation("觀察多方延伸是否成立", "healthy"),
        )
