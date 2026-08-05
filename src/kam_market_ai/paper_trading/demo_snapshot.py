"""Fixed offline data for the Paper Trading morning-session demonstration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PaperTradingDemoSnapshot:
    instrument: str
    snapshot_time: datetime
    current_price: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    volume_ma5: Decimal
    volume_ma10: Decimal
    timeframes: tuple[tuple[str, str], ...]
    u_stage: str
    downside_watch: Decimal
    upside_resistance: Decimal
    data_freshness: str = "DEMO"


DEMO_SNAPSHOT = PaperTradingDemoSnapshot(
    instrument="DEMO-TW", snapshot_time=datetime(2026, 8, 13, 1, 0, tzinfo=UTC),
    current_price=Decimal("100"), open=Decimal("99"), high=Decimal("102"), low=Decimal("98"), close=Decimal("100"),
    volume=Decimal("1200"), volume_ma5=Decimal("1000"), volume_ma10=Decimal("950"),
    timeframes=(("週線", "偏多"), ("日線", "整理"), ("60 分", "偏多"), ("15 分", "等待確認"), ("5 分", "觀望")),
    u_stage="U3：中段整理", downside_watch=Decimal("98"), upside_resistance=Decimal("102"),
)
