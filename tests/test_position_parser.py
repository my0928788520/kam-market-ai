from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from kam_market_ai.positions import PositionDebugWriter, PositionNormalizer, PositionRawAdapter, PositionSide, match_mtx_positions
from kam_market_ai.positions.models import MatchStatus, ParseStatus


def parse(payload: object):
    capture = PositionRawAdapter().capture(payload)  # type: ignore[arg-type]
    normalized = PositionNormalizer().normalize(capture)
    return capture, normalized, match_mtx_positions(normalized)


def test_mtx_long_one_with_decimal_string_fields() -> None:
    _, rows, report = parse({"positions": [{"symbol": "MTX-2026-08", "side": "BUY", "quantity": "1", "avg_price": "21000.50", "market_price": "21010", "floating_pnl": "950"}]})
    row = rows[0]
    assert (row.product_code, row.contract_month, row.side, row.quantity) == ("MTX", "202608", PositionSide.LONG, 1)
    assert (row.average_price, row.current_price, row.unrealized_pnl) == (Decimal("21000.50"), Decimal("21010"), Decimal("950"))
    assert report.status is MatchStatus.SINGLE_MTX_POSITION


def test_mtx_short_one_and_aliases_are_mtx() -> None:
    for symbol in ("MTX-2026-08", "TMF202608", "FITM 2026/08"):
        _, rows, report = parse([{"symbol": symbol, "direction": "SELL", "qty": "1"}])
        assert rows[0].product_code == "MTX"
        assert rows[0].side is PositionSide.SHORT
        assert report.status is MatchStatus.SINGLE_MTX_POSITION
        assert report.positions[0].net_quantity == -1


def test_fubon_single_position_fitm_field_mapping_fixture() -> None:
    payload = json.loads(Path("tests/fixtures/positions/fubon_single_position_fitm.json").read_text(encoding="utf-8"))
    _, rows, report = parse(payload)
    row = rows[0]
    assert (row.product_code, row.contract_month, row.side, row.quantity) == ("MTX", "202608", PositionSide.SHORT, 1)
    assert row.average_price == Decimal("40000.0")
    assert row.current_price == Decimal("39900.0000")
    assert row.unrealized_pnl == Decimal("100.0")
    assert report.status is MatchStatus.SINGLE_MTX_POSITION


def test_mixed_products_only_matches_mtx() -> None:
    _, rows, report = parse([
        {"symbol": "TX-2026-08", "side": "BUY", "quantity": 1},
        {"symbol": "MTX-2026-08", "side": "BUY", "quantity": 1},
    ])
    assert rows[0].product_code == "TX"
    assert report.status is MatchStatus.SINGLE_MTX_POSITION
    assert report.unmatched_source_indexes == (0,)


def test_missing_fields_and_unknown_product_are_not_guessed() -> None:
    _, rows, report = parse([{"symbol": "ABC-2026-08", "quantity": "1"}, {"side": "BUY", "quantity": "1"}])
    assert rows[0].product_code is None
    assert "SIDE_UNKNOWN" in rows[0].warnings
    assert "PRODUCT_UNKNOWN" in rows[1].warnings
    assert report.status is MatchStatus.EMPTY


def test_negative_quantity_and_direction_conflict_are_rejected() -> None:
    _, rows, report = parse([
        {"symbol": "MTX-2026-08", "side": "BUY", "quantity": "-1"},
        {"symbol": "MTX-2026-08", "side": "BUY", "direction": "SELL", "quantity": "1"},
    ])
    assert rows[0].status is ParseStatus.REJECTED
    assert "QUANTITY_NEGATIVE" in rows[0].warnings
    assert rows[1].status is ParseStatus.REJECTED
    assert "SIDE_CONFLICT" in rows[1].warnings
    assert report.status is MatchStatus.UNKNOWN


def test_empty_position_payload() -> None:
    capture, rows, report = parse({"positions": []})
    assert capture.rows == ()
    assert rows == ()
    assert report.status is MatchStatus.EMPTY


def test_opposite_sides_are_not_a_single_position() -> None:
    _, _, report = parse([
        {"symbol": "MTX-2026-08", "side": "BUY", "quantity": "1"},
        {"symbol": "MTX-2026-08", "side": "SELL", "quantity": "1"},
    ])
    assert report.status is MatchStatus.NOT_SINGLE_MTX_POSITION
    assert "OPPOSITE_SIDE_CONFLICT" in report.positions[0].warnings


def test_debug_writer_emits_required_files_and_safe_warnings(tmp_path) -> None:
    capture, rows, report = parse([{"symbol": "MTX-2026-08", "side": "BUY", "quantity": "-1"}])
    directory = tmp_path / "debug" / "position"
    PositionDebugWriter(directory).write(capture, rows, report)
    for name in ("raw_position.json", "normalized_position.json", "matched_position.json", "parser.log"):
        assert (directory / name).is_file()
    raw = json.loads((directory / "raw_position.json").read_text(encoding="utf-8"))
    assert raw["capture"]["rows"][0]["payload"]["symbol"] == "MTX-2026-08"
    assert "QUANTITY_NEGATIVE" in (directory / "parser.log").read_text(encoding="utf-8")
