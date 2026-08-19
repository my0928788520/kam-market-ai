from datetime import UTC, date, datetime
from decimal import Decimal

from kam_market_ai.market_data.taiex_weekly_cycle import (
    TaiexWeeklyCycleSource,
    classify_taiex_weekly_cycle,
)


def _closes(values: list[int]) -> tuple[tuple[date, Decimal], ...]:
    return tuple((date(2026, 1, index + 1), Decimal(value)) for index, value in enumerate(values))


def test_weekly_cycle_uses_taiex_close_and_ma20() -> None:
    result = classify_taiex_weekly_cycle(_closes(list(range(100, 121))))
    assert result.stage in {"U3", "U4", "U5"}
    assert result.source == "TWSE_TAIEX_OFFICIAL_WEEKLY"
    assert result.safe_payload()["live_order_allowed"] is False


def test_source_aggregates_official_daily_rows_into_weeks(tmp_path) -> None:
    calls = 0

    def fetch(_: str) -> object:
        nonlocal calls
        calls += 1
        if calls > 6:
            return {"data": []}
        month = calls
        return {"data": [[f"115/{month:02d}/{day:02d}", "0", "0", "0", str(10000 + calls * 100 + day)] for day in range(1, 29)]}

    result = TaiexWeeklyCycleSource(tmp_path / "taiex.json", fetch).load(
        datetime(2026, 6, 30, tzinfo=UTC)
    )
    assert result.week_end is not None
    assert (tmp_path / "taiex.json").exists()
