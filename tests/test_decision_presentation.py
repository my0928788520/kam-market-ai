from dataclasses import replace

from kam_market_ai.live_read_only.decision_presentation import SelectedSnapshotDecisionPresenter
from kam_market_ai.live_read_only.market_snapshot import (
    OFFLINE_DEMO_MARKET_DATA_SOURCE,
    MarketDataFreshness,
    MarketDataSource,
)


def test_selected_snapshots_have_deterministic_and_distinct_presentations() -> None:
    presenter = SelectedSnapshotDecisionPresenter()
    tx, mtx, tmf = (
        presenter.present(OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot(code))
        for code in ("TX", "MTX", "TMF")
    )
    assert tx.direction.label == "偏多" and tx.next_step.label == "觀察多方延伸是否成立"
    assert mtx.next_step.label == "等待資料恢復" and tmf.next_step.label == "等待市場恢復"
    assert presenter.present(OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TX")) == tx


def test_stale_and_invalid_snapshots_fail_closed() -> None:
    presenter = SelectedSnapshotDecisionPresenter()
    stale = replace(
        OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TX"),
        freshness=MarketDataFreshness.STALE,
        freshness_status=MarketDataFreshness.STALE,
    )
    assert presenter.present(stale).direction.label == "資料不足／無法判讀"
    assert (
        presenter.present(OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("BAD")).next_step.label
        == "等待資料恢復"
    )


def test_fresh_live_tick_never_becomes_a_direction_signal_without_timeframes() -> None:
    presenter = SelectedSnapshotDecisionPresenter()
    live = replace(
        OFFLINE_DEMO_MARKET_DATA_SOURCE.read_snapshot("TX"),
        data_source=MarketDataSource.FUTURE_LIVE,
    )
    result = presenter.present(live)
    assert result.direction.label == "尚未判定"
    assert result.control.bull_score is None
    assert result.cycle.label == "等待四週期資料"
    assert result.next_step.label == "保持觀察"
