from datetime import UTC, datetime
from decimal import Decimal

import pytest

from kam_market_ai.paper_trading.contracts import (
    PaperTradingFill,
    PaperTradingPosition,
    PaperTradingSide,
)
from kam_market_ai.paper_trading.ledger import PaperTradingLedger, apply_paper_fill


NOW = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)


def _fill(side: PaperTradingSide, *, quantity: str = "1", price: str = "100", fees: str = "1") -> PaperTradingFill:
    return PaperTradingFill(
        f"fill-{side.value}", f"order-{side.value}", "TEST", side, Decimal(quantity), Decimal(price), Decimal(fees), NOW
    )


def test_buy_and_sell_keep_cash_and_position_ledgers_consistent() -> None:
    initial = PaperTradingLedger(Decimal("1000"))
    bought = apply_paper_fill(initial, _fill(PaperTradingSide.BUY)).ledger

    assert bought.cash_balance == Decimal("899")
    assert bought.positions[0].quantity == Decimal("1")
    assert bought.positions[0].average_price == Decimal("100")
    assert bought.cash_entries[0].cash_delta == Decimal("-101")

    sold = apply_paper_fill(bought, _fill(PaperTradingSide.SELL, price="110", fees="2")).ledger
    assert sold.cash_balance == Decimal("1007")
    assert sold.positions == ()
    assert sold.cash_entries[-1].cash_delta == Decimal("108")


def test_insufficient_cash_is_atomic_and_source_ledger_is_unchanged() -> None:
    initial = PaperTradingLedger(Decimal("10"))

    with pytest.raises(ValueError, match="INSUFFICIENT_CASH"):
        apply_paper_fill(initial, _fill(PaperTradingSide.BUY))

    assert initial.cash_balance == Decimal("10")
    assert initial.positions == ()
    assert initial.cash_entries == ()


def test_insufficient_position_is_atomic_and_shorting_is_rejected_by_default() -> None:
    initial = PaperTradingLedger(Decimal("1000"))

    with pytest.raises(ValueError, match="INSUFFICIENT_POSITION"):
        apply_paper_fill(initial, _fill(PaperTradingSide.SELL))

    assert initial.cash_balance == Decimal("1000")
    assert initial.positions == ()


def test_short_sell_and_buy_to_cover_keep_ledger_consistent() -> None:
    initial = PaperTradingLedger(Decimal("1000"), allow_short=True)
    shorted = apply_paper_fill(initial, _fill(PaperTradingSide.SELL, price="100")).ledger

    assert shorted.positions[0].quantity == Decimal("-1")
    assert shorted.positions[0].average_price == Decimal("100")
    assert shorted.cash_balance == Decimal("1099")

    covered = apply_paper_fill(
        shorted,
        _fill(PaperTradingSide.BUY, price="90", fees="2"),
    ).ledger
    assert covered.positions == ()
    assert covered.cash_balance == Decimal("1007")


def test_ledger_is_immutable_and_never_exposes_live_capabilities() -> None:
    ledger = PaperTradingLedger(
        Decimal("1000"),
        (PaperTradingPosition("TEST", Decimal("1"), Decimal("100"), Decimal("0"), NOW),),
    )

    with pytest.raises(Exception):
        ledger.cash_balance = Decimal("0")  # type: ignore[misc]

    payload = ledger.canonical_payload()
    assert payload["dry_run"] is True
    assert payload["live_order_allowed"] is False
    assert payload["broker_connected"] is False
    assert payload["account_credentials_allowed"] is False
    assert ledger.ledger_hash == ledger.ledger_hash
