"""Strict MTX matching; incomplete rows never become a position claim."""

from __future__ import annotations

from collections import defaultdict

from .models import MatchStatus, MatchedPosition, MatchedPositionReport, NormalizedFuturesPosition, ParseStatus, PositionSide


def match_mtx_positions(rows: tuple[NormalizedFuturesPosition, ...]) -> MatchedPositionReport:
    eligible: dict[str, list[NormalizedFuturesPosition]] = defaultdict(list)
    unmatched: list[int] = []
    warnings: list[str] = []
    for row in rows:
        if row.product_code != "MTX":
            unmatched.append(row.source_index)
            continue
        if row.status is ParseStatus.REJECTED or row.contract_month is None or row.quantity is None or row.side is PositionSide.UNKNOWN:
            unmatched.append(row.source_index)
            warnings.append(f"MTX_ROW_UNUSABLE:{row.source_index}")
            continue
        eligible[row.contract_month].append(row)
    positions: list[MatchedPosition] = []
    for month, month_rows in sorted(eligible.items()):
        long_quantity = sum(row.quantity or 0 for row in month_rows if row.side is PositionSide.LONG)
        short_quantity = sum(row.quantity or 0 for row in month_rows if row.side is PositionSide.SHORT)
        net = long_quantity - short_quantity
        side = PositionSide.LONG if net > 0 else PositionSide.SHORT if net < 0 else PositionSide.UNKNOWN
        row_warnings: list[str] = []
        if long_quantity and short_quantity:
            row_warnings.append("OPPOSITE_SIDE_CONFLICT")
        positions.append(MatchedPosition(month, long_quantity, short_quantity, net, side,
                                         tuple(row.source_index for row in month_rows), tuple(row_warnings)))
    if not rows:
        status = MatchStatus.EMPTY
    elif not positions:
        status = MatchStatus.UNKNOWN if warnings else MatchStatus.EMPTY
    elif len(positions) == 1 and abs(positions[0].net_quantity) == 1 and not positions[0].warnings and not warnings:
        status = MatchStatus.SINGLE_MTX_POSITION
    else:
        status = MatchStatus.NOT_SINGLE_MTX_POSITION
    return MatchedPositionReport(status, tuple(positions), tuple(unmatched), tuple(dict.fromkeys(warnings)))
