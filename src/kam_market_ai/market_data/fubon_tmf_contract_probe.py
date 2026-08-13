"""One-shot discovery of documented Fubon TMF futures symbols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .fubon_neo import AuthorizedMarketDataClients
from .futures_live_probe import FubonFuturesContractDiscovery, FuturesProductCode


class FubonTmfContractProbeError(RuntimeError):
    """Stable failure without retaining provider payloads."""


@dataclass(frozen=True, slots=True)
class FubonTmfContractCandidate:
    symbol: str
    name: str
    end_date: date

    def safe_payload(self) -> dict[str, str]:
        return {
            "product_code": FuturesProductCode.TMF.value,
            "symbol": self.symbol,
            "name": self.name,
            "end_date": self.end_date.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class FubonTmfContractProbeReport:
    session: str
    candidates: tuple[FubonTmfContractCandidate, ...]

    def safe_payload(self) -> dict[str, object]:
        return {
            "success": True,
            "mode": "one_shot_read_only_tmf_contract_discovery",
            "session": self.session,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.safe_payload() for candidate in self.candidates],
            "endpoint_invoked": True,
            "endpoint_call_count": 1,
            "quote_endpoint_invoked": False,
            "market_data_only": True,
            "account_connected": False,
            "broker_connected": False,
            "trading_enabled": False,
            "live_order_allowed": False,
            "raw_payload_retained": False,
        }


class FubonTmfContractProbe:
    """Call tickers once and retain only strictly validated live TMF rows."""

    def __init__(self, clients: AuthorizedMarketDataClients) -> None:
        if not isinstance(clients, AuthorizedMarketDataClients):
            raise TypeError("AuthorizedMarketDataClients is required")
        self._intraday = clients.futopt_rest.intraday

    def run(
        self,
        *,
        after_hours: bool = False,
        today: date | None = None,
    ) -> FubonTmfContractProbeReport:
        session = "AFTERHOURS" if after_hours else "REGULAR"
        try:
            payload = self._intraday.tickers(
                type="FUTURE",
                exchange="TAIFEX",
                session=session,
                contractType="I",
            )
        # Provider exceptions may contain request internals. Collapse all of
        # them at this boundary instead of retaining or exposing the original.
        except Exception:  # noqa: BLE001
            raise FubonTmfContractProbeError("TICKERS_ENDPOINT_ERROR") from None
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            raise FubonTmfContractProbeError("TICKERS_CONTRACT_ERROR")
        local_today = today or datetime.now(ZoneInfo("Asia/Taipei")).date()
        candidates: list[FubonTmfContractCandidate] = []
        for row in rows:
            identity = FubonFuturesContractDiscovery._validated_identity(
                FuturesProductCode.TMF,
                row,
                local_today,
            )
            if identity is None or not isinstance(row, Mapping):
                continue
            symbol, end_date = identity
            name = row.get("name")
            if isinstance(name, str):
                candidates.append(FubonTmfContractCandidate(symbol, name, end_date))
        candidates.sort(key=lambda item: (item.end_date, item.symbol))
        if not candidates:
            raise FubonTmfContractProbeError("NO_VERIFIED_TMF_CONTRACT")
        return FubonTmfContractProbeReport(session, tuple(candidates))

    def resolve_active(
        self,
        *,
        after_hours: bool = False,
        today: date | None = None,
    ) -> FubonTmfContractCandidate:
        """Resolve one active TMF contract by documented quote volume."""
        report = self.run(after_hours=after_hours, today=today)
        ranked: list[tuple[int, FubonTmfContractCandidate]] = []
        for candidate in report.candidates:
            params: dict[str, object] = {"symbol": candidate.symbol}
            if after_hours:
                params["session"] = "afterhours"
            try:
                payload = self._intraday.quote(**params)
            except Exception:  # noqa: BLE001
                raise FubonTmfContractProbeError("QUOTE_ENDPOINT_ERROR") from None
            total = payload.get("total") if isinstance(payload, Mapping) else None
            volume = total.get("tradeVolume") if isinstance(total, Mapping) else None
            if isinstance(volume, bool) or not isinstance(volume, (int, float)) or volume < 0:
                continue
            ranked.append((int(volume), candidate))
        if not ranked:
            raise FubonTmfContractProbeError("NO_VERIFIED_TMF_QUOTE_VOLUME")
        maximum = max(volume for volume, _ in ranked)
        selected = tuple(candidate for volume, candidate in ranked if volume == maximum)
        if len(selected) != 1:
            raise FubonTmfContractProbeError("AMBIGUOUS_ACTIVE_TMF_CONTRACT")
        return selected[0]
