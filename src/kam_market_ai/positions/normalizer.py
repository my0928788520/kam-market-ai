"""Conservative mapping from raw dictionaries to normalized futures positions."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from .instruments import canonical_month, canonical_product
from .models import NormalizedFuturesPosition, ParseStatus, PositionSide, RawPositionCapture


_FIELDS: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "code", "contract_code", "stock_no"),
    "product": ("product", "product_code", "contract"),
    "month": ("contract_month", "delivery_month", "expiry_date", "month"),
    "side": ("side", "direction", "buy_sell", "bs_action"),
    "quantity": ("quantity", "qty", "volume", "position_qty", "orig_lots", "tradable_lot"),
    "average_price": ("average_price", "avg_price", "cost_price", "price"),
    "current_price": ("current_price", "last_price", "market_price"),
    "unrealized_pnl": ("unrealized_pnl", "floating_pnl", "unrealized_profit_loss", "profit_or_loss"),
}
_LONG = frozenset({"LONG", "BUY", "B", "多", "買"})
_SHORT = frozenset({"SHORT", "SELL", "S", "空", "賣"})


class PositionNormalizer:
    def normalize(self, capture: RawPositionCapture) -> tuple[NormalizedFuturesPosition, ...]:
        return tuple(self._normalize_row(row.source_index, row.payload) for row in capture.rows)

    def _normalize_row(self, source_index: int, row: Mapping[str, Any]) -> NormalizedFuturesPosition:
        warnings: list[str] = []
        symbol = self._text(self._value(row, "symbol", warnings))
        product_raw = self._text(self._value(row, "product", warnings))
        month_raw = self._text(self._value(row, "month", warnings))
        product_code = canonical_product(product_raw) or canonical_product(symbol)
        contract_month = canonical_month(month_raw) or canonical_month(symbol)
        side = self._side(self._value(row, "side", warnings), warnings)
        quantity = self._quantity(self._value(row, "quantity", warnings), warnings)
        average_price = self._decimal(self._value(row, "average_price", warnings), "AVERAGE_PRICE_INVALID", warnings)
        current_price = self._decimal(self._value(row, "current_price", warnings), "CURRENT_PRICE_INVALID", warnings)
        unrealized_pnl = self._decimal(self._value(row, "unrealized_pnl", warnings), "UNREALIZED_PNL_INVALID", warnings)

        if product_code is None:
            warnings.append("PRODUCT_UNKNOWN")
        if product_code == "MTX" and contract_month is None:
            warnings.append("MTX_MONTH_UNKNOWN")
        if side is PositionSide.UNKNOWN:
            warnings.append("SIDE_UNKNOWN")
        if quantity is None:
            warnings.append("QUANTITY_UNKNOWN")
        status = ParseStatus.NORMALIZED if not warnings else ParseStatus.PARTIAL
        if any(code in warnings for code in ("SIDE_CONFLICT", "QUANTITY_NEGATIVE", "QUANTITY_INVALID")):
            status = ParseStatus.REJECTED
        return NormalizedFuturesPosition(
            source_index=source_index, symbol_raw=symbol, product_raw=product_raw,
            product_code=product_code, contract_month=contract_month, side=side, quantity=quantity,
            average_price=average_price, current_price=current_price, unrealized_pnl=unrealized_pnl,
            status=status, warnings=tuple(dict.fromkeys(warnings)),
        )

    def _value(self, row: Mapping[str, Any], field: str, warnings: list[str]) -> Any:
        values = [(key, row[key]) for key in _FIELDS[field] if key in row and row[key] not in (None, "")]
        if not values:
            return None
        first_key, first = values[0]
        if any(value != first for _, value in values[1:]):
            warnings.append(f"{field.upper()}_CONFLICT")
        return first

    @staticmethod
    def _text(value: Any) -> str | None:
        if isinstance(value, (str, int)):
            normalized = str(value).strip()
            return normalized or None
        return None

    @staticmethod
    def _side(value: Any, warnings: list[str]) -> PositionSide:
        if not isinstance(value, str):
            return PositionSide.UNKNOWN
        normalized = value.strip().upper().split(".")[-1]
        if normalized in _LONG:
            return PositionSide.LONG
        if normalized in _SHORT:
            return PositionSide.SHORT
        return PositionSide.UNKNOWN

    @staticmethod
    def _quantity(value: Any, warnings: list[str]) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        try:
            decimal = Decimal(str(value).strip())
        except (InvalidOperation, AttributeError):
            warnings.append("QUANTITY_INVALID")
            return None
        if decimal < 0:
            warnings.append("QUANTITY_NEGATIVE")
            return None
        if decimal != decimal.to_integral_value():
            warnings.append("QUANTITY_INVALID")
            return None
        return int(decimal)

    @staticmethod
    def _decimal(value: Any, error_code: str, warnings: list[str]) -> Decimal | None:
        if value in (None, "") or isinstance(value, bool):
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, AttributeError):
            warnings.append(error_code)
            return None
