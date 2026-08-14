"""Read-only chart bridge with local normalized-candle continuity."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from math import isfinite
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

from kam_market_ai.live_read_only.market_snapshot import (
    MarketDataFreshness,
    MarketDataSource,
    MarketSnapshot,
    MarketSnapshotStatus,
    TradingSession,
)
from kam_market_ai.models import Candle, Instrument
from kam_market_ai.paper_trading.multi_timeframe_chart import ChartCandle, ChartSeries

from .fubon_five_timeframe_pipeline import (
    CompleteFiveTimeframeCandleResult,
    FiveTimeframe,
    FiveTimeframeCandleResult,
)
from .fubon_neo import AuthorizedMarketDataClients
from .index_futures_product import index_futures_product, infer_index_futures_instrument


class FubonLiveQuoteError(ValueError):
    """Sanitized failure from the read-only intraday quote boundary."""


TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True, slots=True)
class LiveChartPrice:
    instrument: str
    symbol: str
    price: float
    observed_at: datetime
    volume: int | None = None

    def __post_init__(self) -> None:
        if self.instrument not in {"TX", "MTX", "TMF"} or not self.symbol or self.symbol.strip() != self.symbol:
            raise ValueError("live chart price identity is invalid")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("live chart price must be finite and positive")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("live chart price timestamp must be timezone-aware")
        if self.volume is not None and (
            isinstance(self.volume, bool) or not isinstance(self.volume, int) or self.volume < 0
        ):
            raise ValueError("live chart volume must be a non-negative integer")


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
        instrument: Instrument | str | None = None,
        after_hours: bool = False,
    ) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        if not symbol or symbol.strip() != symbol:
            raise ValueError("verified futures symbol is required")
        self._intraday = clients.futopt_rest.intraday
        self._symbol = symbol
        self._instrument = instrument if isinstance(instrument, Instrument) else (
            Instrument(str(instrument).upper()) if instrument is not None else infer_index_futures_instrument(symbol)
        )
        index_futures_product(self._instrument)
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
        total = payload.get("total")
        raw_volume = total.get("tradeVolume") if isinstance(total, Mapping) else None
        volume = None
        if raw_volume is not None:
            if (
                isinstance(raw_volume, bool)
                or not isinstance(raw_volume, (int, float))
                or not isfinite(float(raw_volume))
                or raw_volume < 0
            ):
                raise FubonLiveQuoteError("QUOTE_VOLUME_INVALID")
            volume = int(raw_volume)
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise FubonLiveQuoteError("QUOTE_PRICE_INVALID")
        normalized_price = float(price)
        if not isfinite(normalized_price) or normalized_price <= 0:
            raise FubonLiveQuoteError("QUOTE_PRICE_INVALID")
        return LiveChartPrice(
            self._instrument.value,
            self._symbol,
            normalized_price,
            _provider_timestamp(observed_at),
            volume,
        )


def _contract_month_from_symbol(symbol: str, *, reference: datetime) -> str:
    product = index_futures_product(infer_index_futures_instrument(symbol))
    if (
        len(symbol) < 5
        or not symbol.startswith(product.symbol_prefix)
        or not symbol[-2].isalpha()
        or not symbol[-1].isdigit()
    ):
        raise ValueError("verified index-futures symbol is required")
    month = ord(symbol[-2].upper()) - ord("A") + 1
    if not 1 <= month <= 12:
        raise ValueError("verified index-futures contract month is invalid")
    decade = reference.year - reference.year % 10
    year = decade + int(symbol[-1])
    if year < reference.year - 1:
        year += 10
    elif year > reference.year + 8:
        year -= 10
    return f"{year:04d}{month:02d}"


class FubonLiveDashboardMarketSource:
    """Project the latest normalized TMF quote into the read-only dashboard contract."""

    mode = "fubon-live"

    def __init__(
        self,
        quote_source: FubonLiveQuoteSource,
        *,
        symbol: str,
        instrument: Instrument | str | None = None,
        contract_month: str | None = None,
        after_hours: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        stale_after_seconds: int = 60,
        expire_after_seconds: int = 300,
    ) -> None:
        if not isinstance(quote_source, FubonLiveQuoteSource):
            raise TypeError("FubonLiveQuoteSource is required")
        if not callable(clock):
            raise TypeError("dashboard market clock must be callable")
        if stale_after_seconds < 0 or expire_after_seconds < stale_after_seconds:
            raise ValueError("dashboard quote freshness thresholds are invalid")
        reference = clock()
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("dashboard market clock must be timezone-aware")
        inferred_month = contract_month or _contract_month_from_symbol(
            symbol,
            reference=reference,
        )
        if len(inferred_month) != 6 or not inferred_month.isdigit():
            raise ValueError("dashboard contract month must use YYYYMM")
        self._quote_source = quote_source
        self._instrument = instrument if isinstance(instrument, Instrument) else (
            Instrument(str(instrument).upper()) if instrument is not None else infer_index_futures_instrument(symbol)
        )
        self._product = index_futures_product(self._instrument)
        self._symbol = symbol
        self._contract_month = inferred_month
        self._after_hours = bool(after_hours)
        self._clock = clock
        self._stale_after_seconds = stale_after_seconds
        self._expire_after_seconds = expire_after_seconds

    def _failure_snapshot(self, product_code: str) -> MarketSnapshot:
        return MarketSnapshot(
            product_code,
            self._product.display_name if product_code == self._instrument.value else "",
            f"{self._product.contract_prefix}{self._contract_month}" if product_code == self._instrument.value else None,
            self._contract_month if product_code == self._instrument.value else None,
            None,
            TradingSession.UNKNOWN,
            "CLIENT_UNAVAILABLE",
            None,
            None,
            None,
            None,
            None,
            None,
            MarketDataSource.FUTURE_LIVE,
            MarketDataFreshness.UNKNOWN,
            (
                MarketSnapshotStatus.CLIENT_UNAVAILABLE
                if product_code == self._instrument.value
                else MarketSnapshotStatus.INVALID_PRODUCT
            ),
            None,
            None,
            None,
            MarketDataFreshness.UNKNOWN,
        )

    def read_snapshot(self, product_code: str) -> MarketSnapshot:
        if product_code != self._instrument.value:
            return self._failure_snapshot(product_code)
        quote = self._quote_source.latest
        if quote is None or quote.symbol != self._symbol:
            return self._failure_snapshot(product_code)
        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return self._failure_snapshot(product_code)
        observed_at = max(observed_at, quote.observed_at)
        age_seconds = int((observed_at - quote.observed_at).total_seconds())
        freshness = (
            MarketDataFreshness.FRESH
            if age_seconds <= self._stale_after_seconds
            else MarketDataFreshness.STALE
            if age_seconds <= self._expire_after_seconds
            else MarketDataFreshness.EXPIRED
        )
        return MarketSnapshot(
            self._instrument.value,
            self._product.display_name,
            f"{self._product.contract_prefix}{self._contract_month}",
            self._contract_month,
            quote.observed_at,
            TradingSession.NIGHT if self._after_hours else TradingSession.DAY,
            "OPEN",
            None,
            None,
            None,
            None,
            Decimal(str(quote.price)),
            Decimal(quote.volume) if quote.volume is not None else None,
            MarketDataSource.FUTURE_LIVE,
            freshness,
            MarketSnapshotStatus.READY,
            observed_at,
            quote.observed_at,
            age_seconds,
            freshness,
        )

    def list_available_products(self) -> tuple[str, ...]:
        return (self._instrument.value,)

    def runtime_status(self) -> str:
        return (
            "READY"
            if self.read_snapshot(self._instrument.value).status is MarketSnapshotStatus.READY
            else "DEGRADED"
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
        closed_higher_timeframe_provider: (
            Callable[[], Mapping[FiveTimeframe, tuple[Candle, ...]]] | None
        ) = None,
        after_hours: bool = False,
        history_path: str | Path | None = None,
        history_15m_path: str | Path | None = None,
        history_limit: int = 240,
        instrument: Instrument | str = Instrument.TMF,
    ) -> None:
        if not callable(result_provider):
            raise TypeError("result_provider must be callable")
        self._result_provider = result_provider
        self._instrument = instrument if isinstance(instrument, Instrument) else Instrument(str(instrument).upper())
        index_futures_product(self._instrument)
        if current_price_provider is not None and not callable(current_price_provider):
            raise TypeError("current_price_provider must be callable")
        self._current_price_provider = current_price_provider
        if closed_higher_timeframe_provider is not None and not callable(
            closed_higher_timeframe_provider
        ):
            raise TypeError("closed_higher_timeframe_provider must be callable")
        self._closed_higher_timeframe_provider = closed_higher_timeframe_provider
        self._closed_higher_timeframes: dict[FiveTimeframe, tuple[Candle, ...]] = {}
        self._closed_higher_timeframes_loaded = False
        self._after_hours = bool(after_hours)
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
        if not isinstance(value, LiveChartPrice) or value.instrument != self._instrument.value:
            return None
        return value

    def _series(
        self,
        instrument: str,
        timeframe: str,
        candles: tuple[ChartCandle, ...],
        source: str,
        updated_at: datetime | None,
        *,
        last_candle_is_forming: bool = False,
        forming_label: str | None = None,
    ) -> ChartSeries:
        current = self._current_price()
        if current is None:
            return ChartSeries(
                instrument,
                timeframe,
                candles,
                source,
                updated_at,
                last_candle_is_forming=last_candle_is_forming,
                forming_label=forming_label,
                trading_session="afterhours" if self._after_hours else "regular",
            )
        return ChartSeries(
            instrument,
            timeframe,
            candles,
            f"{source}+fubon-live-quote",
            updated_at,
            current.price,
            current.observed_at,
            last_candle_is_forming,
            forming_label,
            "afterhours" if self._after_hours else "regular",
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

    def _load_history(self, path: Path | None, timeframe: str) -> tuple[ChartCandle, ...]:
        if path is None or not path.is_file():
            return ()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("schema") != "kam-normalized-chart-history-v1"
                or payload.get("instrument") != self._instrument.value
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
            "instrument": self._instrument.value,
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

    def _refresh_closed_higher_timeframes(self) -> None:
        provider = self._closed_higher_timeframe_provider
        if provider is None:
            return
        try:
            supplied = provider()
            if not isinstance(supplied, Mapping):
                return
            normalized: dict[FiveTimeframe, tuple[Candle, ...]] = {}
            for selected in (FiveTimeframe.DAY, FiveTimeframe.WEEK):
                values = supplied.get(selected)
                if not isinstance(values, tuple) or not values:
                    return
                if any(
                    not isinstance(item, Candle)
                    or item.instrument is not self._instrument
                    or item.start.tzinfo is None
                    or item.start.utcoffset() is None
                    for item in values
                ):
                    return
                ordered = tuple(sorted(values, key=lambda item: item.start))
                if len({item.start for item in ordered}) != len(ordered):
                    return
                normalized[selected] = ordered
        except Exception:  # noqa: BLE001
            return
        with self._lock:
            self._closed_higher_timeframes = normalized
            self._closed_higher_timeframes_loaded = True

    def _closed_higher_candles(
        self,
        result: FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None,
        selected: FiveTimeframe,
    ) -> tuple[ChartCandle, ...]:
        with self._lock:
            values = self._closed_higher_timeframes.get(selected, ())
        if values:
            return tuple(
                ChartCandle(item.start, item.open, item.high, item.low, item.close, item.volume)
                for item in values
            )
        return self._chart_candles(result, selected)

    @staticmethod
    def _next_weekday(value: date) -> date:
        candidate = value + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate

    def _session_start_date(self, observed_at: datetime) -> date | None:
        local = observed_at.astimezone(TAIPEI)
        clock = local.timetz().replace(tzinfo=None)
        if self._after_hours:
            if clock >= time(15):
                return local.date()
            if clock < time(5):
                return local.date() - timedelta(days=1)
            return None
        if time(8, 45) <= clock <= time(13, 45):
            return local.date()
        return None

    def _provisional_day_candle(
        self,
        result: FiveTimeframeCandleResult | CompleteFiveTimeframeCandleResult | None,
        closed_days: tuple[ChartCandle, ...],
    ) -> ChartCandle | None:
        current = self._current_price()
        if current is None or result is None or FiveTimeframe.M15 not in result.series:
            return None
        session_start_date = self._session_start_date(current.observed_at)
        if session_start_date is None:
            return None
        session_candles = tuple(
            item
            for item in result.series[FiveTimeframe.M15]
            if self._session_start_date(item.start) == session_start_date
            and item.start <= current.observed_at
        )
        if not session_candles:
            return None
        trading_date = (
            self._next_weekday(session_start_date) if self._after_hours else session_start_date
        )
        opened_at = datetime.combine(trading_date, time.min, TAIPEI).astimezone(UTC)
        if closed_days and opened_at <= closed_days[-1].opened_at:
            return None
        prices_high = [item.high for item in session_candles]
        prices_low = [item.low for item in session_candles]
        return ChartCandle(
            opened_at,
            session_candles[0].open,
            max(*prices_high, current.price),
            min(*prices_low, current.price),
            current.price,
            sum(item.volume for item in session_candles),
        )

    @staticmethod
    def _provisional_week_candle(
        closed_weeks: tuple[ChartCandle, ...],
        closed_days: tuple[ChartCandle, ...],
        provisional_day: ChartCandle,
    ) -> ChartCandle | None:
        trading_date = provisional_day.opened_at.astimezone(TAIPEI).date()
        week_start = trading_date - timedelta(days=trading_date.weekday())
        opened_at = datetime.combine(week_start, time.min, TAIPEI).astimezone(UTC)
        if closed_weeks and opened_at <= closed_weeks[-1].opened_at:
            return None
        current_week_days = tuple(
            item
            for item in closed_days
            if item.opened_at.astimezone(TAIPEI).date() >= week_start
            and item.opened_at < provisional_day.opened_at
        )
        values = (*current_week_days, provisional_day)
        return ChartCandle(
            opened_at,
            values[0].open,
            max(item.high for item in values),
            min(item.low for item in values),
            provisional_day.close,
            sum(item.volume for item in values),
        )

    def capture_latest(self) -> None:
        """Persist normalized verified 15/60-minute candles, never provider payloads."""
        self._refresh_closed_higher_timeframes()
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
                merged = {item.opened_at: item for item in self._load_history(path, label)}
                merged.update({item.opened_at: item for item in live})
                bounded = tuple(sorted(merged.values(), key=lambda item: item.opened_at))[
                    -self._history_limit :
                ]
                self._write_history(path, label, bounded)

    def read_series(self, instrument: str, timeframe: str) -> ChartSeries:
        mapping = {
            "15m": FiveTimeframe.M15,
            "60m": FiveTimeframe.M60,
            "1d": FiveTimeframe.DAY,
            "1w": FiveTimeframe.WEEK,
        }
        selected = mapping.get(timeframe)
        if instrument != self._instrument.value or selected is None:
            return ChartSeries(instrument, timeframe, (), "invalid-selection", None)
        result = self._result_provider()
        if selected in {FiveTimeframe.DAY, FiveTimeframe.WEEK}:
            with self._lock:
                higher_loaded = self._closed_higher_timeframes_loaded
            if not higher_loaded:
                self._refresh_closed_higher_timeframes()
            closed_days = self._closed_higher_candles(result, FiveTimeframe.DAY)
            closed_weeks = self._closed_higher_candles(result, FiveTimeframe.WEEK)
            base = closed_days if selected is FiveTimeframe.DAY else closed_weeks
            provisional_day = self._provisional_day_candle(result, closed_days)
            provisional = provisional_day
            forming_label = "本日形成中"
            if selected is FiveTimeframe.WEEK and provisional_day is not None:
                provisional = self._provisional_week_candle(
                    closed_weeks,
                    closed_days,
                    provisional_day,
                )
                forming_label = "本週形成中"
            if provisional is not None:
                session_label = "night" if self._after_hours else "regular"
                candles = (*base, provisional)[-self._history_limit :]
                current = self._current_price()
                updated_at = current.observed_at if current is not None else provisional.opened_at
                return self._series(
                    instrument,
                    timeframe,
                    candles,
                    f"taifex-official-closed+fubon-live:provisional-{session_label}",
                    updated_at,
                    last_candle_is_forming=True,
                    forming_label=forming_label,
                )
            if base:
                return self._series(
                    instrument,
                    timeframe,
                    base[-self._history_limit :],
                    "taifex-official-closed:no-current-forming-candle",
                    max(item.opened_at for item in base),
                )
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
        latest_closed_at = max((item.end for item in values), default=None)
        return self._series(
            instrument,
            timeframe,
            live,
            "fubon-live:verified-candles",
            latest_closed_at,
        )


__all__ = [
    "FubonLiveChartSource",
    "FubonLiveDashboardMarketSource",
    "FubonLiveQuoteError",
    "FubonLiveQuoteSource",
    "LiveChartPrice",
]
