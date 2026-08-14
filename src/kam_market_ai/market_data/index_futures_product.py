"""Canonical settings for the three TAIFEX index-futures sizes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kam_market_ai.models import Instrument


@dataclass(frozen=True, slots=True)
class IndexFuturesProduct:
    instrument: Instrument
    symbol_prefix: str
    contract_prefix: str
    display_name: str
    point_value: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal


INDEX_FUTURES_PRODUCTS = {
    Instrument.TX: IndexFuturesProduct(
        Instrument.TX, "TXF", "TXF", "臺股期貨", Decimal("200"), Decimal("701000"), Decimal("538000")
    ),
    Instrument.MTX: IndexFuturesProduct(
        Instrument.MTX, "MXF", "MXF", "小型臺指期貨", Decimal("50"), Decimal("175250"), Decimal("134500")
    ),
    Instrument.TMF: IndexFuturesProduct(
        Instrument.TMF, "TMF", "TMF", "微型臺指期貨", Decimal("10"), Decimal("35050"), Decimal("26900")
    ),
}


def index_futures_product(instrument: Instrument | str) -> IndexFuturesProduct:
    try:
        canonical = instrument if isinstance(instrument, Instrument) else Instrument(str(instrument).upper())
        return INDEX_FUTURES_PRODUCTS[canonical]
    except (KeyError, ValueError):
        raise ValueError("TX, MTX, or TMF instrument is required") from None


def infer_index_futures_instrument(symbol: str) -> Instrument:
    if not symbol or symbol.strip() != symbol:
        raise ValueError("verified futures symbol is required")
    for product in INDEX_FUTURES_PRODUCTS.values():
        if symbol.upper().startswith(product.symbol_prefix):
            return product.instrument
    raise ValueError("verified TXF, MXF, or TMF symbol is required")


__all__ = [
    "INDEX_FUTURES_PRODUCTS",
    "IndexFuturesProduct",
    "index_futures_product",
    "infer_index_futures_instrument",
]
