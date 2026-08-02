"""Deterministic, research-only market-data provider contract.

This module defines data boundaries only.  It performs no I/O and contains no
provider implementation, credentials, network client, or trading capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from json import dumps


MARKET_DATA_PROVIDER_CONTRACT_VERSION = "1.0"


class ResearchSourceKind(StrEnum):
    FIXTURE = "fixture"
    REPLAY = "replay"


class MarketDataTimeframe(StrEnum):
    M5 = "5m"
    M15 = "15m"
    M60 = "60m"
    DAY = "1d"
    WEEK = "1w"


class ProviderResponseStatus(StrEnum):
    READY = "ready"
    INSUFFICIENT_DATA = "insufficient_data"
    BLOCKED = "blocked"


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware.")


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal.")


@dataclass(frozen=True, slots=True)
class MarketDataProviderContract:
    provider_id: str
    provider_version: str
    source_kind: ResearchSourceKind
    supported_timeframes: tuple[MarketDataTimeframe, ...]
    contract_version: str = MARKET_DATA_PROVIDER_CONTRACT_VERSION
    research_only: bool = True
    network_enabled: bool = False
    live_provider_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.provider_version.strip():
            raise ValueError("provider_id and provider_version must be non-empty.")
        if self.contract_version != MARKET_DATA_PROVIDER_CONTRACT_VERSION:
            raise ValueError("Unsupported Market Data Provider Contract version.")
        if not self.supported_timeframes or tuple(sorted(set(self.supported_timeframes), key=str)) != self.supported_timeframes:
            raise ValueError("supported_timeframes must be a non-empty canonical tuple.")
        if self.source_kind not in {ResearchSourceKind.FIXTURE, ResearchSourceKind.REPLAY}:
            raise ValueError("Only research fixture or replay sources are allowed.")
        if self.research_only is not True or self.network_enabled is not False or self.live_provider_enabled is not False:
            raise ValueError("Market data provider contracts are research-only and offline.")


@dataclass(frozen=True, slots=True)
class MarketDataRequest:
    provider_id: str
    instrument: str
    timeframe: MarketDataTimeframe
    start_at: datetime
    end_at: datetime
    as_of: datetime
    request_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.instrument.strip() or not self.request_version.strip():
            raise ValueError("provider_id, instrument, and request_version must be non-empty.")
        _aware(self.start_at, "start_at")
        _aware(self.end_at, "end_at")
        _aware(self.as_of, "as_of")
        if self.start_at >= self.end_at:
            raise ValueError("start_at must be before end_at.")


@dataclass(frozen=True, slots=True)
class MarketDataBar:
    instrument: str
    timeframe: MarketDataTimeframe
    opened_at: datetime
    closed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    source_record_id: str
    closed: bool = True

    def __post_init__(self) -> None:
        if not self.instrument.strip() or not self.source_record_id.strip():
            raise ValueError("instrument and source_record_id must be non-empty.")
        _aware(self.opened_at, "opened_at")
        _aware(self.closed_at, "closed_at")
        if self.opened_at >= self.closed_at:
            raise ValueError("opened_at must be before closed_at.")
        for name, value in (("open", self.open), ("high", self.high), ("low", self.low), ("close", self.close)):
            _decimal(value, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent.")
        if self.volume is not None:
            _decimal(self.volume, "volume")
            if self.volume < 0:
                raise ValueError("volume must be non-negative.")


@dataclass(frozen=True, slots=True)
class MarketDataProviderResponse:
    provider: MarketDataProviderContract
    request: MarketDataRequest
    status: ProviderResponseStatus
    bars: tuple[MarketDataBar, ...]
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.provider.provider_id != self.request.provider_id:
            raise ValueError("Provider and request IDs must match.")
        if self.request.timeframe not in self.provider.supported_timeframes:
            raise ValueError("Requested timeframe is not supported.")
        if tuple(sorted(set(self.issue_codes))) != self.issue_codes or any(not code for code in self.issue_codes):
            raise ValueError("issue_codes must be a canonical non-empty-string tuple.")
        if self.status is ProviderResponseStatus.READY and (not self.bars or self.issue_codes):
            raise ValueError("READY responses require bars and no issues.")
        if self.status is not ProviderResponseStatus.READY and not self.issue_codes:
            raise ValueError("Non-ready responses require issue codes.")
        prior_key: tuple[datetime, str] | None = None
        for bar in self.bars:
            if not bar.closed:
                raise ValueError("Only closed research bars are allowed.")
            if bar.instrument != self.request.instrument or bar.timeframe is not self.request.timeframe:
                raise ValueError("Bar instrument/timeframe must match the request.")
            if not (self.request.start_at <= bar.opened_at and bar.closed_at <= self.request.end_at):
                raise ValueError("Bar is outside the requested time range.")
            if bar.closed_at > self.request.as_of:
                raise ValueError("Bar closed after the as_of boundary.")
            key = (bar.opened_at, bar.source_record_id)
            if prior_key is not None and key <= prior_key:
                raise ValueError("bars must be strictly canonical and unique.")
            prior_key = key

    def canonical_payload(self) -> dict[str, object]:
        return {
            "contract_version": self.provider.contract_version,
            "provider": {
                "id": self.provider.provider_id,
                "version": self.provider.provider_version,
                "source_kind": self.provider.source_kind.value,
                "supported_timeframes": [item.value for item in self.provider.supported_timeframes],
                "research_only": True,
                "network_enabled": False,
                "live_provider_enabled": False,
            },
            "request": {
                "provider_id": self.request.provider_id,
                "instrument": self.request.instrument,
                "timeframe": self.request.timeframe.value,
                "start_at": _utc(self.request.start_at),
                "end_at": _utc(self.request.end_at),
                "as_of": _utc(self.request.as_of),
                "request_version": self.request.request_version,
            },
            "status": self.status.value,
            "bars": [
                {
                    "instrument": bar.instrument,
                    "timeframe": bar.timeframe.value,
                    "opened_at": _utc(bar.opened_at),
                    "closed_at": _utc(bar.closed_at),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": None if bar.volume is None else str(bar.volume),
                    "source_record_id": bar.source_record_id,
                    "closed": True,
                }
                for bar in self.bars
            ],
            "issue_codes": list(self.issue_codes),
        }

    @property
    def response_hash(self) -> str:
        payload = dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(payload.encode("utf-8")).hexdigest()
