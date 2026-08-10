"""Safe reflection probe for the authorized Fubon futures history surface.

The probe never invokes a market-data endpoint.  It records only public member
names and the Python signature exposed by ``futopt_rest.historical.candles`` so
an SDK-specific mapper can be implemented from retained evidence, not guesses.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .fubon_neo import AuthorizedMarketDataClients


class HistoricalContractProbeError(RuntimeError):
    """Raised when the SDK does not expose the expected read-only surface."""


def _public_members(value: object) -> tuple[str, ...]:
    try:
        names = dir(value)
    except Exception as error:
        raise HistoricalContractProbeError("PUBLIC_MEMBER_DISCOVERY_FAILED") from error
    return tuple(sorted(name for name in names if name and not name.startswith("_")))


def _safe_signature(value: object) -> tuple[Mapping[str, str], ...]:
    if not callable(value):
        raise HistoricalContractProbeError("CANDLES_NOT_CALLABLE")
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError) as error:
        raise HistoricalContractProbeError("CANDLES_SIGNATURE_UNAVAILABLE") from error
    parameters: list[Mapping[str, str]] = []
    for parameter in signature.parameters.values():
        parameters.append(
            {
                "name": parameter.name,
                "kind": parameter.kind.name,
                "required": str(parameter.default is inspect.Parameter.empty).lower(),
            }
        )
    return tuple(parameters)


@dataclass(frozen=True, slots=True)
class HistoricalContractFingerprint:
    schema_version: str
    mode: str
    trading_enabled: bool
    endpoint_invoked: bool
    historical_members: tuple[str, ...]
    candles_parameters: tuple[Mapping[str, str], ...]
    fingerprint_sha256: str

    def safe_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "trading_enabled": self.trading_enabled,
            "endpoint_invoked": self.endpoint_invoked,
            "historical_members": list(self.historical_members),
            "candles_parameters": [dict(item) for item in self.candles_parameters],
            "fingerprint_sha256": self.fingerprint_sha256,
        }


def probe_fubon_historical_contract(
    clients: AuthorizedMarketDataClients,
) -> HistoricalContractFingerprint:
    """Inspect the futures history API without calling it or retaining SDK objects."""
    if not isinstance(clients, AuthorizedMarketDataClients):
        raise HistoricalContractProbeError("AUTHORIZED_CLIENTS_REQUIRED")
    try:
        historical = clients.futopt_rest.historical
        candles = historical.candles
    except Exception as error:
        raise HistoricalContractProbeError("HISTORICAL_CANDLES_UNAVAILABLE") from error
    members = _public_members(historical)
    parameters = _safe_signature(candles)
    canonical = {
        "schema_version": "1.0",
        "historical_members": list(members),
        "candles_parameters": [dict(item) for item in parameters],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return HistoricalContractFingerprint(
        schema_version="1.0",
        mode="read_only_contract_probe",
        trading_enabled=False,
        endpoint_invoked=False,
        historical_members=members,
        candles_parameters=parameters,
        fingerprint_sha256=digest,
    )


__all__ = [
    "HistoricalContractFingerprint",
    "HistoricalContractProbeError",
    "probe_fubon_historical_contract",
]
