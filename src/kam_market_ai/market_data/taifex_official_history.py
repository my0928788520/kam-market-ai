"""Fail-closed TAIFEX history for the live five-timeframe observer.

The source uses only public, read-only TAIFEX downloads.  It builds a
deterministic unadjusted continuous TMF series by selecting the non-spread
contract with the greatest regular-session volume on each trading date.  The
current Taipei trading date and current trading week are never certified as
closed.
"""

from __future__ import annotations

import csv
import json
import re
import threading
from collections import defaultdict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from io import BytesIO, TextIOWrapper
from math import isfinite
from os import replace as atomic_replace
from pathlib import Path
from types import MappingProxyType
from typing import cast
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

from kam_market_ai.models import Candle, Instrument

from .fubon_five_timeframe_pipeline import FiveTimeframe
from .verified_higher_timeframe_aggregation import (
    VerifiedTradingDay,
    VerifiedTradingWeek,
    aggregate_verified_week,
)
from .verified_higher_timeframe_batch import VerifiedHigherTimeframeBatchResult

TAIPEI = ZoneInfo("Asia/Taipei")
TAIFEX_DAILY_DOWNLOAD_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
TAIFEX_INTRADAY_LIST_URL = (
    "https://www.taifex.com.tw/cht/3/dlFutPrevious30DaysSalesData"
)
TAIFEX_INTRADAY_PREFIX = (
    "https://www.taifex.com.tw/file/taifex/Dailydownload/"
    "DailydownloadCSV/"
)
TAIFEX_HISTORY_SCHEMA = "kam-taifex-official-history-v2"
_CACHE_TIMEFRAMES = (
    FiveTimeframe.M5,
    FiveTimeframe.M15,
    FiveTimeframe.M60,
    FiveTimeframe.DAY,
)
_MINIMUM_COUNTS = {
    FiveTimeframe.M5: 60,
    FiveTimeframe.M15: 48,
    FiveTimeframe.M60: 36,
    FiveTimeframe.DAY: 45,
    FiveTimeframe.WEEK: 39,
}
_ZIP_URL_PATTERN = re.compile(
    re.escape(TAIFEX_INTRADAY_PREFIX)
    + r"Daily_(\d{4})_(\d{2})_(\d{2})\.zip"
)


class TaifexOfficialHistoryError(RuntimeError):
    """Stable error that never includes a remote response or local secret."""


Transport = Callable[[str, bytes | None, int], bytes]


def _canonical_hash(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _default_transport(url: str, data: bytes | None, maximum_bytes: int) -> bytes:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.taifex.com.tw"
        or not parsed.path.startswith(("/cht/3/", "/file/taifex/Dailydownload/"))
    ):
        raise TaifexOfficialHistoryError("TAIFEX_HISTORY_UNAPPROVED_ENDPOINT")
    headers = {
        "User-Agent": "kam-market-ai/0.1 read-only historical verifier",
        "Accept": "text/html,application/zip,text/csv,*/*;q=0.1",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urlopen(Request(url, data=data, headers=headers), timeout=45) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > maximum_bytes:
                raise TaifexOfficialHistoryError("TAIFEX_HISTORY_RESPONSE_TOO_LARGE")
            payload = cast(bytes, response.read(maximum_bytes + 1))
    except TaifexOfficialHistoryError:
        raise
    except Exception as error:
        raise TaifexOfficialHistoryError("TAIFEX_HISTORY_TRANSPORT_ERROR") from error
    if not payload or len(payload) > maximum_bytes:
        raise TaifexOfficialHistoryError("TAIFEX_HISTORY_RESPONSE_SIZE_INVALID")
    return payload


@dataclass(frozen=True, slots=True)
class _DailyRow:
    trading_date: date
    contract_month: str
    opening: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class TaifexOfficialHistoryResult:
    intraday_series: Mapping[FiveTimeframe, tuple[Candle, ...]]
    higher_timeframes: VerifiedHigherTimeframeBatchResult
    source_trading_dates: tuple[date, ...]
    selected_contract_months: tuple[str, ...]
    source_hash: str
    refreshed_at: datetime
    official_request_count: int
    cache_hit: bool = False
    source_kind: str = "TAIFEX_OFFICIAL_REGULAR_SESSION_HISTORY"
    continuous_contract_policy: str = "MAX_REGULAR_SESSION_VOLUME_PER_TRADING_DATE"

    def __post_init__(self) -> None:
        if tuple(self.intraday_series) != _CACHE_TIMEFRAMES[:3]:
            raise ValueError("TAIFEX_HISTORY_INTRADAY_TIMEFRAMES_INVALID")
        if self.higher_timeframes.instrument is not Instrument.TMF:
            raise ValueError("TAIFEX_HISTORY_INSTRUMENT_INVALID")
        if not self.source_trading_dates or len(self.source_trading_dates) != len(
            self.selected_contract_months
        ):
            raise ValueError("TAIFEX_HISTORY_SOURCE_IDENTITY_INVALID")
        if any(current <= previous for previous, current in zip(
            self.source_trading_dates,
            self.source_trading_dates[1:],
            strict=False,
        )):
            raise ValueError("TAIFEX_HISTORY_DATES_NOT_CHRONOLOGICAL")
        counts = {
            **{item: len(values) for item, values in self.intraday_series.items()},
            FiveTimeframe.DAY: len(self.higher_timeframes.day_candles),
            FiveTimeframe.WEEK: len(self.higher_timeframes.week_candles),
        }
        if any(counts[item] < minimum for item, minimum in _MINIMUM_COUNTS.items()):
            raise ValueError("TAIFEX_HISTORY_INSUFFICIENT_VERIFIED_CANDLES")
        if self.refreshed_at.tzinfo is None or self.refreshed_at.utcoffset() is None:
            raise ValueError("TAIFEX_HISTORY_REFRESH_TIMEZONE_REQUIRED")
        if len(self.source_hash) != 64 or self.official_request_count < 0:
            raise ValueError("TAIFEX_HISTORY_AUDIT_IDENTITY_INVALID")

    def safe_payload(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "continuous_contract_policy": self.continuous_contract_policy,
            "session": "regular",
            "coverage_start": self.source_trading_dates[0].isoformat(),
            "coverage_end": self.source_trading_dates[-1].isoformat(),
            "source_trading_date_count": len(self.source_trading_dates),
            "candle_counts": {
                **{
                    timeframe.value: len(values)
                    for timeframe, values in self.intraday_series.items()
                },
                "1d": len(self.higher_timeframes.day_candles),
                "1w": len(self.higher_timeframes.week_candles),
            },
            "source_hash": self.source_hash,
            "refreshed_at": self.refreshed_at.isoformat(),
            "official_request_count": self.official_request_count,
            "cache_hit": self.cache_hit,
            "market_data_only": True,
            "trading_enabled": False,
            "live_order_allowed": False,
            "raw_payload_retained": False,
        }


def _number(value: str) -> float | None:
    stripped = value.strip().replace(",", "")
    if stripped in {"", "-", "NULL"}:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return None
    return number if isfinite(number) and number > 0 else None


def _volume(value: str) -> int | None:
    stripped = value.strip().replace(",", "")
    try:
        number = int(stripped)
    except ValueError:
        return None
    return number if number >= 0 else None


def _parse_daily_csv(payload: bytes, local_date: date) -> tuple[_DailyRow, ...]:
    try:
        text = payload.decode("cp950")
    except UnicodeDecodeError as error:
        raise TaifexOfficialHistoryError("TAIFEX_DAILY_ENCODING_INVALID") from error
    rows = csv.reader(text.splitlines())
    try:
        header = next(rows)
    except StopIteration as error:
        raise TaifexOfficialHistoryError("TAIFEX_DAILY_EMPTY") from error
    if len(header) < 18 or header[0].strip() != "交易日期":
        raise TaifexOfficialHistoryError("TAIFEX_DAILY_HEADER_INVALID")
    values: list[_DailyRow] = []
    for row in rows:
        if len(row) < 18 or row[1].strip() != "TMF" or row[17].strip() != "一般":
            continue
        contract_month = row[2].strip()
        if not contract_month.isdigit() or len(contract_month) != 6:
            continue
        try:
            trading_date = date.fromisoformat(row[0].strip().replace("/", "-"))
        except ValueError:
            continue
        if trading_date >= local_date:
            continue
        opening, high, low, close = (_number(row[index]) for index in (3, 4, 5, 6))
        volume = _volume(row[9])
        if None in {opening, high, low, close, volume}:
            continue
        assert opening is not None and high is not None and low is not None and close is not None
        assert volume is not None
        if low > min(opening, close) or high < max(opening, close) or low > high:
            continue
        values.append(
            _DailyRow(trading_date, contract_month, opening, high, low, close, volume)
        )
    return tuple(values)


def _select_active_daily_rows(rows: tuple[_DailyRow, ...]) -> tuple[_DailyRow, ...]:
    grouped: dict[date, list[_DailyRow]] = defaultdict(list)
    for row in rows:
        grouped[row.trading_date].append(row)
    selected: list[_DailyRow] = []
    for trading_date in sorted(grouped):
        ranked = sorted(grouped[trading_date], key=lambda item: item.volume, reverse=True)
        if len(ranked) > 1 and ranked[0].volume == ranked[1].volume:
            raise TaifexOfficialHistoryError("TAIFEX_DAILY_ACTIVE_CONTRACT_AMBIGUOUS")
        selected.append(ranked[0])
    return tuple(selected)


def _daily_candle(row: _DailyRow) -> Candle:
    # Analysis timing treats the candle duration as its expected recurrence.
    # Keep the official OHLC/volume while representing the certified trading
    # date as one canonical 24-hour period.
    start = datetime.combine(row.trading_date, time(0, 0), TAIPEI).astimezone(UTC)
    end = (datetime.combine(row.trading_date, time(0, 0), TAIPEI) + timedelta(days=1)).astimezone(UTC)
    return Candle(
        Instrument.TMF,
        start,
        end,
        row.opening,
        row.high,
        row.low,
        row.close,
        row.volume,
    )


def _build_higher_timeframes(
    daily_candles: tuple[Candle, ...],
    *,
    local_date: date,
) -> VerifiedHigherTimeframeBatchResult:
    days: list[VerifiedTradingDay] = []
    for candle in daily_candles:
        trading_date = candle.start.astimezone(TAIPEI).date()
        week_start = trading_date - timedelta(days=trading_date.weekday())
        days.append(VerifiedTradingDay(trading_date, week_start, (candle,), True))
    by_week: dict[date, list[VerifiedTradingDay]] = defaultdict(list)
    for day in days:
        if day.week_start + timedelta(days=7) <= local_date:
            by_week[day.week_start].append(day)
    weeks = tuple(
        VerifiedTradingWeek(week_start, tuple(by_week[week_start]), True)
        for week_start in sorted(by_week)
    )
    week_candles = []
    for week in weeks:
        aggregated = aggregate_verified_week(week)
        start = datetime.combine(week.week_start, time(0, 0), TAIPEI).astimezone(UTC)
        week_candles.append(Candle(
            Instrument.TMF,
            start,
            start + timedelta(days=7),
            aggregated.open,
            aggregated.high,
            aggregated.low,
            aggregated.close,
            aggregated.volume,
        ))
    return VerifiedHigherTimeframeBatchResult(
        instrument=Instrument.TMF,
        days=tuple(days),
        weeks=weeks,
        day_candles=daily_candles,
        week_candles=tuple(week_candles),
    )


def _parse_trade_time(value: str) -> time | None:
    stripped = value.strip()
    if len(stripped) != 6 or not stripped.isdigit():
        return None
    try:
        return time(int(stripped[:2]), int(stripped[2:4]), int(stripped[4:]))
    except ValueError:
        return None


def _aggregate_trades(
    trades: tuple[tuple[datetime, float, int], ...],
    interval_minutes: int,
) -> tuple[Candle, ...]:
    buckets: dict[datetime, list[tuple[datetime, float, int]]] = defaultdict(list)
    session_start = trades[0][0].replace(hour=8, minute=45, second=0, microsecond=0)
    session_end = session_start + timedelta(hours=5)
    for observed_at, price, quantity in trades:
        elapsed = int((observed_at - session_start).total_seconds() // 60)
        if observed_at == session_end:
            elapsed -= 1
        if elapsed < 0 or elapsed >= 300:
            continue
        bucket_start = session_start + timedelta(
            minutes=(elapsed // interval_minutes) * interval_minutes
        )
        buckets[bucket_start].append((observed_at, price, quantity))
    candles: list[Candle] = []
    for start in sorted(buckets):
        values = buckets[start]
        prices = [item[1] for item in values]
        candles.append(
            Candle(
                Instrument.TMF,
                start.astimezone(UTC),
                (start + timedelta(minutes=interval_minutes)).astimezone(UTC),
                prices[0],
                max(prices),
                min(prices),
                prices[-1],
                sum(item[2] for item in values),
            )
        )
    return tuple(candles)


def _parse_intraday_zip(
    payload: bytes,
    trading_date: date,
) -> Mapping[FiveTimeframe, tuple[Candle, ...]]:
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as error:
        raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_ZIP_INVALID") from error
    with archive:
        members = tuple(
            item for item in archive.infolist()
            if not item.is_dir() and item.filename.lower().endswith(".csv")
        )
        if len(members) != 1 or members[0].file_size > 128_000_000:
            raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_ZIP_CONTENT_INVALID")
        by_contract: dict[str, list[tuple[datetime, float, int]]] = defaultdict(list)
        expected_date = trading_date.strftime("%Y%m%d")
        with (
            archive.open(members[0]) as binary,
            TextIOWrapper(binary, encoding="cp950", newline="") as text,
        ):
            rows = csv.reader(text)
            try:
                header = next(rows)
            except StopIteration as error:
                raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_EMPTY") from error
            if len(header) < 6 or header[0].strip() != "成交日期":
                raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_HEADER_INVALID")
            for row in rows:
                if (
                    len(row) < 6
                    or row[0].strip() != expected_date
                    or row[1].strip() != "TMF"
                ):
                    continue
                contract_month = row[2].strip()
                if not contract_month.isdigit() or len(contract_month) != 6:
                    continue
                observed_time = _parse_trade_time(row[3])
                price = _number(row[4])
                quantity = _volume(row[5])
                if observed_time is None or price is None or quantity is None:
                    continue
                if not time(8, 45) <= observed_time <= time(13, 45):
                    continue
                observed_at = datetime.combine(trading_date, observed_time, TAIPEI)
                by_contract[contract_month].append((observed_at, price, quantity))
    if not by_contract:
        raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_TMF_TRADES_MISSING")
    totals = sorted(
        ((sum(item[2] for item in values), contract) for contract, values in by_contract.items()),
        reverse=True,
    )
    if len(totals) > 1 and totals[0][0] == totals[1][0]:
        raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_ACTIVE_CONTRACT_AMBIGUOUS")
    trades = tuple(sorted(by_contract[totals[0][1]], key=lambda item: item[0]))
    if not trades:
        raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_ACTIVE_TRADES_EMPTY")
    return MappingProxyType({
        FiveTimeframe.M5: _aggregate_trades(trades, 5),
        FiveTimeframe.M15: _aggregate_trades(trades, 15),
        FiveTimeframe.M60: _aggregate_trades(trades, 60),
    })


def _candle_payload(candle: Candle) -> dict[str, object]:
    return {
        "start": candle.start.isoformat(),
        "end": candle.end.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _decode_candle(value: object) -> Candle:
    if not isinstance(value, Mapping):
        raise TypeError("TAIFEX_HISTORY_CACHE_CANDLE_INVALID")
    start = datetime.fromisoformat(str(value.get("start")))
    end = datetime.fromisoformat(str(value.get("end")))
    numbers = tuple(float(value[name]) for name in ("open", "high", "low", "close"))
    volume = int(value["volume"])
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or end <= start
        or any(not isfinite(item) or item <= 0 for item in numbers)
        or volume < 0
    ):
        raise ValueError("TAIFEX_HISTORY_CACHE_CANDLE_INVALID")
    opening, high, low, close = numbers
    if low > min(opening, close) or high < max(opening, close) or low > high:
        raise ValueError("TAIFEX_HISTORY_CACHE_CANDLE_INVALID")
    return Candle(Instrument.TMF, start, end, opening, high, low, close, volume)


class TaifexOfficialHistorySource:
    """Download, cache and certify closed regular-session TMF history."""

    def __init__(
        self,
        cache_path: str | Path,
        *,
        transport: Transport | None = None,
        daily_lookback_days: int = 420,
        intraday_trading_days: int = 12,
        workers: int = 4,
    ) -> None:
        if daily_lookback_days < 330 or not 8 <= intraday_trading_days <= 30:
            raise ValueError("TAIFEX_HISTORY_LOOKBACK_INVALID")
        if not 1 <= workers <= 4:
            raise ValueError("TAIFEX_HISTORY_WORKER_COUNT_INVALID")
        self.cache_path = Path(cache_path)
        self._transport = transport or _default_transport
        self._daily_lookback_days = daily_lookback_days
        self._intraday_trading_days = intraday_trading_days
        self._workers = workers
        self._lock = threading.Lock()
        self._memory: tuple[date, TaifexOfficialHistoryResult] | None = None

    def fetch(
        self,
        *,
        observed_at: datetime,
        after_hours: bool = False,
    ) -> TaifexOfficialHistoryResult:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("TAIFEX_HISTORY_OBSERVED_AT_TIMEZONE_REQUIRED")
        if after_hours:
            raise TaifexOfficialHistoryError("TAIFEX_AFTER_HOURS_HISTORY_NOT_CERTIFIED")
        local_date = observed_at.astimezone(TAIPEI).date()
        with self._lock:
            if self._memory is not None and self._memory[0] == local_date:
                return replace(self._memory[1], official_request_count=0, cache_hit=True)
            try:
                cached = self._load_cache(local_date)
            except TaifexOfficialHistoryError:
                # This cache is replaceable public market data.  Never use a
                # failed hash, but allow a fresh official download to replace it.
                cached = None
            if cached is not None:
                self._memory = (local_date, cached)
                return cached
            try:
                result = self._refresh(local_date, observed_at)
                self._write_cache(result, local_date)
            except TaifexOfficialHistoryError:
                raise
            except Exception as error:
                raise TaifexOfficialHistoryError("TAIFEX_HISTORY_REFRESH_ERROR") from error
            self._memory = (local_date, result)
            return result

    def _refresh(
        self,
        local_date: date,
        observed_at: datetime,
    ) -> TaifexOfficialHistoryResult:
        chunks: list[tuple[date, date]] = []
        start = local_date - timedelta(days=self._daily_lookback_days)
        final = local_date
        while start <= final:
            end = min(final, start + timedelta(days=27))
            chunks.append((start, end))
            start = end + timedelta(days=1)

        def daily_download(chunk: tuple[date, date]) -> bytes:
            left, right = chunk
            data = urlencode({
                "down_type": "1",
                "queryStartDate": left.strftime("%Y/%m/%d"),
                "queryEndDate": right.strftime("%Y/%m/%d"),
                "commodity_id": "TMF",
                "commodity_id2": "",
            }).encode("ascii")
            return self._transport(TAIFEX_DAILY_DOWNLOAD_URL, data, 2_000_000)

        with ThreadPoolExecutor(max_workers=self._workers) as executor:
            daily_payloads = tuple(executor.map(daily_download, chunks))
        daily_rows: dict[tuple[date, str], _DailyRow] = {}
        for payload in daily_payloads:
            for row in _parse_daily_csv(payload, local_date):
                key = (row.trading_date, row.contract_month)
                previous = daily_rows.setdefault(key, row)
                if previous != row:
                    raise TaifexOfficialHistoryError("TAIFEX_DAILY_DUPLICATE_CONFLICT")
        active_days = _select_active_daily_rows(tuple(daily_rows.values()))
        daily_candles = tuple(_daily_candle(row) for row in active_days)
        higher = _build_higher_timeframes(daily_candles, local_date=local_date)

        listing = self._transport(TAIFEX_INTRADAY_LIST_URL, None, 2_000_000)
        try:
            listing_text = listing.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_LIST_ENCODING_INVALID") from error
        dated_urls = {
            date(int(year), int(month), int(day)): (
                f"{TAIFEX_INTRADAY_PREFIX}Daily_{year}_{month}_{day}.zip"
            )
            for year, month, day in _ZIP_URL_PATTERN.findall(listing_text)
            if date(int(year), int(month), int(day)) < local_date
        }
        selected_dates = tuple(sorted(dated_urls)[-self._intraday_trading_days:])
        if len(selected_dates) != self._intraday_trading_days:
            raise TaifexOfficialHistoryError("TAIFEX_INTRADAY_LIST_INSUFFICIENT")

        def intraday_download(trading_date: date) -> bytes:
            return self._transport(dated_urls[trading_date], None, 5_000_000)

        with ThreadPoolExecutor(max_workers=self._workers) as executor:
            intraday_payloads = tuple(executor.map(intraday_download, selected_dates))
        intraday: dict[FiveTimeframe, list[Candle]] = {
            timeframe: [] for timeframe in _CACHE_TIMEFRAMES[:3]
        }
        for trading_date, payload in zip(selected_dates, intraday_payloads, strict=True):
            parsed = _parse_intraday_zip(payload, trading_date)
            for timeframe, candles in parsed.items():
                intraday[timeframe].extend(candles)
        intraday_series = MappingProxyType({
            timeframe: tuple(sorted(candles, key=lambda candle: candle.start))
            for timeframe, candles in intraday.items()
        })
        source_dates = tuple(row.trading_date for row in active_days)
        contract_months = tuple(row.contract_month for row in active_days)
        audit = {
            "schema": TAIFEX_HISTORY_SCHEMA,
            "source_trading_dates": [item.isoformat() for item in source_dates],
            "selected_contract_months": list(contract_months),
            "intraday_dates": [item.isoformat() for item in selected_dates],
            "series": {
                **{
                    timeframe.value: [_candle_payload(item) for item in candles]
                    for timeframe, candles in intraday_series.items()
                },
                "1d": [_candle_payload(item) for item in daily_candles],
                "1w": [_candle_payload(item) for item in higher.week_candles],
            },
        }
        return TaifexOfficialHistoryResult(
            intraday_series,
            higher,
            source_dates,
            contract_months,
            _canonical_hash(audit),
            observed_at.astimezone(UTC),
            len(chunks) + 1 + len(selected_dates),
        )

    def _write_cache(self, result: TaifexOfficialHistoryResult, local_date: date) -> None:
        payload = {
            "schema": TAIFEX_HISTORY_SCHEMA,
            "refreshed_local_date": local_date.isoformat(),
            "refreshed_at": result.refreshed_at.isoformat(),
            "source_trading_dates": [item.isoformat() for item in result.source_trading_dates],
            "selected_contract_months": list(result.selected_contract_months),
            "series": {
                **{
                    timeframe.value: [_candle_payload(item) for item in candles]
                    for timeframe, candles in result.intraday_series.items()
                },
                "1d": [
                    _candle_payload(item) for item in result.higher_timeframes.day_candles
                ],
            },
            "source_hash": result.source_hash,
        }
        payload["cache_hash"] = _canonical_hash(payload)
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        atomic_replace(temporary, self.cache_path)

    def _load_cache(self, local_date: date) -> TaifexOfficialHistoryResult | None:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise TaifexOfficialHistoryError("TAIFEX_HISTORY_CACHE_INVALID") from error
        if not isinstance(payload, dict):
            raise TaifexOfficialHistoryError("TAIFEX_HISTORY_CACHE_INVALID")
        if payload.get("schema") != TAIFEX_HISTORY_SCHEMA:
            return None
        cache_hash = payload.pop("cache_hash", None)
        if cache_hash != _canonical_hash(payload):
            raise TaifexOfficialHistoryError("TAIFEX_HISTORY_CACHE_HASH_MISMATCH")
        if payload.get("refreshed_local_date") != local_date.isoformat():
            return None
        try:
            series_payload = payload["series"]
            if not isinstance(series_payload, Mapping):
                raise TypeError
            intraday = MappingProxyType({
                timeframe: tuple(
                    _decode_candle(item) for item in series_payload[timeframe.value]
                )
                for timeframe in _CACHE_TIMEFRAMES[:3]
            })
            daily = tuple(_decode_candle(item) for item in series_payload["1d"])
            source_dates = tuple(
                date.fromisoformat(item) for item in payload["source_trading_dates"]
            )
            contract_months = tuple(str(item) for item in payload["selected_contract_months"])
            refreshed_at = datetime.fromisoformat(str(payload["refreshed_at"]))
            source_hash = str(payload["source_hash"])
            higher = _build_higher_timeframes(daily, local_date=local_date)
            return TaifexOfficialHistoryResult(
                intraday,
                higher,
                source_dates,
                contract_months,
                source_hash,
                refreshed_at,
                0,
                True,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TaifexOfficialHistoryError("TAIFEX_HISTORY_CACHE_INVALID") from error


__all__ = [
    "TAIFEX_DAILY_DOWNLOAD_URL",
    "TAIFEX_HISTORY_SCHEMA",
    "TAIFEX_INTRADAY_LIST_URL",
    "TAIFEX_INTRADAY_PREFIX",
    "TaifexOfficialHistoryError",
    "TaifexOfficialHistoryResult",
    "TaifexOfficialHistorySource",
]
