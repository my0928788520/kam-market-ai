"""Read-only chart bridge with local normalized-candle continuity."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from threading import Lock

from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle, ChartSeries

from .fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)
from .fubon_neo import AuthorizedMarketDataClients


class FubonLiveQuoteError(ValueError):
    """Sanitized failure from the read-only intraday quote boundary."""


@dataclass(frozen=True, slots=True)
class LiveChartPrice:
    instrument: str
    symbol: str
    price: float
    observed_at: datetime

    def __post_init__(self) -> None:
        if self.instrument != "TMF" or not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("live chart price identity is invalid")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("live chart price must be finite and positive")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("live chart price timestamp must be timezone-aware")


def _provider_timestamp(value: object) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FubonLiveQuoteError("QUOTE_TIMESTAMP_INVALID")
    numeric = float(value)
    if not isfinite(numeric) or numeric <= 0:
        raise FubonLiveQuoteError("QUOTE_TIMESTAMP_INVALID")
    if numeric > 100_000_000_000_000:
        numeric /= 1_000_000
    elif numeric > 100_000_000_000:
        numeric /= 1_000
    try:
        return datetime.fromtimestamp(numeric, tz=UTC)
    except (OverflowError, OSError, ValueError):
        raise FubonLiveQuoteError("QUOTE_TIMESTAMP_INVALID") from None


class FubonLiveQuoteSource:
    """Keep only the latest normalized TMF trade from the documented quote API."""

    def __init__(
        self,
        clients: AuthorizedMarketDataClients,
        *,
        symbol: str,
        after_hours: bool = False,
    ) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        if not symbol or symbol.strip() != symbol:
            raise ValueError("verified futures symbol is required")
        self._intraday = clients.futopt_rest.intraday
        self._symbol = symbol
        self._after_hours = after_hours
        self._latest: LiveChartPrice | None = None
        self._lock = Lock()

    @property
    def latest(self) -> LiveChartPrice | None:
        with self._lock:
            return self._latest

    def refresh(self) -> LiveChartPrice:
        request: dict[str, object] = {"symbol": self._symbol}
        if self._after_hours:
            request["session"] = "afterhours"
        try:
            payload = self._intraday.quote(**request)
        except Exception:  # noqa: BLE001
            raise FubonLiveQuoteError("QUOTE_ENDPOINT_ERROR") from None
        value = self._decode(payload)
        with self._lock:
            if self._latest is None or value.observed_at >= self._latest.observed_at:
                self._latest = value
            return self._latest

    def refresh_safely(self) -> bool:
        try:
            self.refresh()
        except (FubonLiveQuoteError, TypeError, ValueError):
            return False
        return True

    def _decode(self, payload: object) -> LiveChartPrice:
        if not isinstance(payload, Mapping) or payload.get("symbol") != self._symbol:
            raise FubonLiveQuoteError("QUOTE_IDENTITY_MISMATCH")
        last_trade = payload.get("lastTrade")
        if isinstance(last_trade, Mapping):
            price = last_trade.get("price")
            observed_at = last_trade.get("time")
        else:
            price = payload.get("closePrice")
            observed_at = payload.get("closeTime")
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise FubonLiveQuoteError("QUOTE_PRICE_INVALID")
        normalized_price = float(price)
        if not isfinite(normalized_price) or normalized_price <= 0:
            raise FubonLiveQuoteError("QUOTE_PRICE_INVALID")
        return LiveChartPrice(
            "TMF",
            self._symbol,
            normalized_price,
            _provider_timestamp(observed_at),
        )


class FubonLiveChartSource:
    """Merge verified live candles into a bounded local normalized history."""

    def __init__(
        self,
        result_provider: Callable[
            [], FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None
        ],
        *,
        current_price_provider: Callable[[], LiveChartPrice | None] | None = None,
        history_path: str | Path | None = None,
        history_15m_path: str | Path | None = None,
        history_limit: int = 240,
    ) -> None:
        if not callable(result_provider):
            raise TypeError("result_provider must be callable")
        self._result_provider = result_provider
        if current_price_provider is not None and not callable(current_price_provider):
            raise TypeError("current_price_provider must be callable")
        self._current_price_provider = current_price_provider
        if isinstance(history_limit, bool) or history_limit < 20:
            raise ValueError("history_limit must be at least 20")
        self._history_paths = {
            FiveTimeframe.M15: Path(history_15m_path) if history_15m_path is not None else None,
            FiveTimeframe.M60: Path(history_path) if history_path is not None else None,
        }
        self._history_limit = history_limit
        self._lock = Lock()

    def _current_price(self) -> LiveChartPrice | None:
        if self._current_price_provider is None:
            return None
        try:
            value = self._current_price_provider()
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(value, LiveChartPrice) or value.instrument != "TMF":
            return None
        return value

    def _series(
        self,
        instrument: str,
        timeframe: str,
        candles: tuple[ChartCandle, ...],
        source: str,
        updated_at: datetime | None,
    ) -> ChartSeries:
        current = self._current_price()
        if current is None:
            return ChartSeries(instrument, timeframe, candles, source, updated_at)
        return ChartSeries(
            instrument,
            timeframe,
            candles,
            f"{source}+fubon-live-quote",
            updated_at,
            current.price,
            current.observed_at,
        )

    @staticmethod
    def _chart_candles(
        result: FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None,
        selected: FiveTimeframe,
    ) -> tuple[ChartCandle, ...]:
        if result is None or selected not in result.series:
            return ()
        return tuple(
            ChartCandle(item.start, item.open, item.high, item.low, item.close, item.volume)
            for item in result.series[selected]
        )

    def _load_history(
        self, path: Path | None, timeframe: str
    ) -> tuple[ChartCandle, ...]:
        if path is None or not path.is_file():
            return ()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("schema") != "kam-normalized-chart-history-v1"
                or payload.get("instrument") != "TMF"
                or payload.get("timeframe") != timeframe
            ):
                return ()
            return tuple(
                ChartCandle(
                    datetime.fromisoformat(row["opened_at"]),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                )
                for row in payload["candles"]
            )
        except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
            return ()

    def _write_history(
        self, path: Path | None, timeframe: str, candles: tuple[ChartCandle, ...]
    ) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "kam-normalized-chart-history-v1",
            "instrument": "TMF",
            "timeframe": timeframe,
            "candles": [
                {
                    "opened_at": item.opened_at.isoformat(),
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                }
                for item in candles
            ],
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def capture_latest(self) -> None:
        """Persist normalized verified 15/60-minute candles, never provider payloads."""
        result = self._result_provider()
        with self._lock:
            for selected, label in (
                (FiveTimeframe.M15, "15m"),
                (FiveTimeframe.M60, "60m"),
            ):
                path = self._history_paths[selected]
                live = self._chart_candles(result, selected)
                if not live or path is None:
                    continue
                merged = {
                    item.opened_at: item for item in self._load_history(path, label)
                }
                merged.update({item.opened_at: item for item in live})
                bounded = tuple(
                    sorted(merged.values(), key=lambda item: item.opened_at)
                )[-self._history_limit:]
                self._write_history(path, label, bounded)

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        mapping = {
            "15m": FiveTimeframe.M15,
            "60m": FiveTimeframe.M60,
            "1d": FiveTimeframe.DAY,
            "1w": FiveTimeframe.WEEK,
        }
        selected = mapping.get(timeframe)
        if instrument != "TMF" or selected is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        result = self._result_provider()
        live = self._chart_candles(result, selected)
        history_path = self._history_paths.get(selected)
        if history_path is not None:
            self.capture_latest()
            with self._lock:
                history = self._load_history(history_path, timeframe)
            if history:
                return self._series(
                    instrument,
                    timeframe,
                    history,
                    "fubon-live:normalized-local-history",
                    max(item.opened_at for item in history),
                )
        if not live:
            return self._series(
                instrument,
                timeframe,
                (),
                "fubon-live:not-yet-verified",
                None,
            )
        assert result is not None
        values = result.series[selected]
        updated_at = max((item.end for item in values), default=None)
        return self._series(
            instrument,
            timeframe,
            live,
            "fubon-live:verified-candles",
            updated_at,
        )


__all__ = [
    "FubonLiveChartSource",
    "FubonLiveQuoteError",
    "FubonLiveQuoteSource",
    "LiveChartPrice",
]
