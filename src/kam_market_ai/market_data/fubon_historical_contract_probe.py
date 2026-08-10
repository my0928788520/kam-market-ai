"""Safe reflection probe for the authorized Fubon futures history surface.

The probe never invokes a market-data endpoint.  It records only public member
names and the Python signature exposed by ``futopt_rest.historical.candles`` so
an SDK-specific mapper can be implemented from retained evidence, not guesses.
"""

from __future__ import annotations

import dis
import hashlib
import inspect
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import metadata
from typing import Any

from .fubon_neo import AuthorizedMarketDataClients


class HistoricalContractProbeError(RuntimeError):
    """Raised when the SDK does not expose the expected read-only surface."""


_SAFE_LITERAL = re.compile(r"^[A-Za-z0-9_./{}:+-]{1,120}$")
_FORBIDDEN_LITERAL_PARTS = ("account", "apikey", "cert", "password", "secret", "token")
_SAFE_PACKAGE_VALUE = re.compile(r"^[A-Za-z0-9_.+-]{1,80}$")


def _official_futures_contract_evidence() -> Mapping[str, Any]:
    """Return the allow-listed support boundary published by Fubon.

    The official futures/option Web API documentation currently advertises
    intraday data only.  Its candle contract therefore cannot authorize the
    SDK's otherwise-undocumented ``futopt.historical`` surface.
    """
    return {
        "publisher": "Fubon Securities",
        "documentation_checked_on": "2026-08-10",
        "getting_started_url": (
            "https://www.fbs.com.tw/TradeAPI/docs/market-data-future/"
            "http-api/getting-started/"
        ),
        "candles_url": (
            "https://www.fbs.com.tw/TradeAPI/docs/market-data-future/"
            "http-api/intraday/candles/"
        ),
        "documented_data_types": ["intraday"],
        "documented_candles_endpoint": "intraday/candles/{symbol}",
        "documented_request_parameters": ["symbol", "session", "timeframe"],
        "documented_response_fields": [
            "date",
            "type",
            "exchange",
            "market",
            "symbol",
            "timeframe",
            "data",
        ],
        "documented_candle_fields": [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "average",
        ],
        "historical_candles_documented": False,
        "historical_adapter_authorized": False,
    }


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


def _callable_evidence(value: object, *, error_prefix: str) -> Mapping[str, Any]:
    """Return deterministic code metadata without retaining or invoking ``value``."""
    if not callable(value):
        raise HistoricalContractProbeError(f"{error_prefix}_NOT_CALLABLE")
    evidence: dict[str, Any] = {
        "module": str(getattr(value, "__module__", "")),
        "qualname": str(getattr(value, "__qualname__", "")),
        "type_module": type(value).__module__,
        "type_qualname": type(value).__qualname__,
        "parameters": [dict(item) for item in _safe_signature(value)],
    }
    code = getattr(value, "__code__", None)
    if code is None:
        evidence.update({"code_available": False, "code_names": [], "safe_code_strings": []})
        return evidence
    code_names = sorted({str(name) for name in code.co_names if str(name).isidentifier()})
    safe_strings = sorted(
        {
            item
            for item in code.co_consts
            if isinstance(item, str)
            and _SAFE_LITERAL.fullmatch(item)
            and not item.lower().startswith(("http:", "https:"))
            and not any(part in item.lower() for part in _FORBIDDEN_LITERAL_PARTS)
        }
    )
    evidence.update(
        {
            "code_available": True,
            "code_names": code_names,
            "safe_code_strings": safe_strings,
            "bytecode_sha256": hashlib.sha256(code.co_code).hexdigest(),
        }
    )
    try:
        source = inspect.getsource(value)
    except (OSError, TypeError):
        evidence["source_sha256"] = None
    else:
        evidence["source_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return evidence


def _instruction_evidence(value: object) -> tuple[Mapping[str, Any], ...]:
    """Return sanitized bytecode instructions without constants that may hold secrets."""
    code = getattr(value, "__code__", None)
    if code is None:
        return ()
    safe: list[Mapping[str, Any]] = []
    try:
        instructions = dis.get_instructions(value)
    except (TypeError, ValueError) as error:
        raise HistoricalContractProbeError("CANDLES_INSTRUCTIONS_UNAVAILABLE") from error
    for instruction in instructions:
        item: dict[str, Any] = {"opname": instruction.opname}
        argument = instruction.argval
        if isinstance(argument, str):
            if (
                _SAFE_LITERAL.fullmatch(argument)
                and not argument.lower().startswith(("http:", "https:"))
                and not any(part in argument.lower() for part in _FORBIDDEN_LITERAL_PARTS)
            ):
                item["safe_arg"] = argument
        elif isinstance(argument, int) and instruction.opname in {
            "BUILD_MAP",
            "BUILD_STRING",
            "BUILD_TUPLE",
            "CALL",
            "CALL_FUNCTION_EX",
            "CALL_METHOD",
            "DICT_MERGE",
            "DICT_UPDATE",
            "PRECALL",
        }:
            item["safe_arg"] = argument
        safe.append(item)
    return tuple(safe)


def _documentation_evidence(value: object) -> Mapping[str, Any]:
    """Describe callable documentation without retaining its prose."""
    document = inspect.getdoc(value)
    annotations = getattr(value, "__annotations__", {})
    annotation_names = (
        sorted(str(name) for name in annotations if str(name).isidentifier())
        if isinstance(annotations, Mapping)
        else []
    )
    return {
        "docstring_available": bool(document),
        "docstring_sha256": (
            hashlib.sha256(document.encode("utf-8")).hexdigest() if document else None
        ),
        "annotation_names": annotation_names,
    }


def _sdk_package_evidence() -> Mapping[str, Any]:
    """Return allow-listed distribution metadata without exposing install paths."""
    try:
        distribution = metadata.distribution("fugle-marketdata")
    except metadata.PackageNotFoundError:
        return {
            "distribution_available": False,
            "name": None,
            "version": None,
            "typed_marker_present": False,
            "stub_files": [],
        }
    raw_name = distribution.metadata.get("Name", "")
    raw_version = distribution.version
    name = raw_name if _SAFE_PACKAGE_VALUE.fullmatch(raw_name) else None
    version = raw_version if _SAFE_PACKAGE_VALUE.fullmatch(raw_version) else None
    files = tuple(str(item).replace("\\", "/") for item in (distribution.files or ()))
    stubs = sorted(
        item
        for item in files
        if item.startswith("fugle_marketdata/") and item.endswith(".pyi")
    )
    return {
        "distribution_available": True,
        "name": name,
        "version": version,
        "typed_marker_present": "fugle_marketdata/py.typed" in files,
        "stub_files": stubs,
    }


@dataclass(frozen=True, slots=True)
class HistoricalContractFingerprint:
    schema_version: str
    mode: str
    trading_enabled: bool
    endpoint_invoked: bool
    historical_members: tuple[str, ...]
    candles_parameters: tuple[Mapping[str, str], ...]
    candles_evidence: Mapping[str, Any]
    candles_instructions: tuple[Mapping[str, Any], ...]
    candles_documentation: Mapping[str, Any]
    sdk_package_evidence: Mapping[str, Any]
    official_futures_contract_evidence: Mapping[str, Any]
    request_evidence: Mapping[str, Any]
    config_members: tuple[str, ...]
    fingerprint_sha256: str

    def safe_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "trading_enabled": self.trading_enabled,
            "endpoint_invoked": self.endpoint_invoked,
            "historical_members": list(self.historical_members),
            "candles_parameters": [dict(item) for item in self.candles_parameters],
            "candles_evidence": dict(self.candles_evidence),
            "candles_instructions": [dict(item) for item in self.candles_instructions],
            "candles_documentation": dict(self.candles_documentation),
            "sdk_package_evidence": dict(self.sdk_package_evidence),
            "official_futures_contract_evidence": dict(
                self.official_futures_contract_evidence
            ),
            "request_evidence": dict(self.request_evidence),
            "config_members": list(self.config_members),
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
        request = historical.request
        config = historical.config
    except Exception as error:
        raise HistoricalContractProbeError("HISTORICAL_CANDLES_UNAVAILABLE") from error
    members = _public_members(historical)
    parameters = _safe_signature(candles)
    candles_evidence = _callable_evidence(candles, error_prefix="CANDLES")
    candles_instructions = _instruction_evidence(candles)
    candles_documentation = _documentation_evidence(candles)
    sdk_package_evidence = _sdk_package_evidence()
    official_futures_contract_evidence = _official_futures_contract_evidence()
    request_evidence = _callable_evidence(request, error_prefix="REQUEST")
    config_members = _public_members(config)
    canonical = {
        "schema_version": "5.0",
        "historical_members": list(members),
        "candles_parameters": [dict(item) for item in parameters],
        "candles_evidence": candles_evidence,
        "candles_instructions": [dict(item) for item in candles_instructions],
        "candles_documentation": candles_documentation,
        "sdk_package_evidence": sdk_package_evidence,
        "official_futures_contract_evidence": official_futures_contract_evidence,
        "request_evidence": request_evidence,
        "config_members": list(config_members),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return HistoricalContractFingerprint(
        schema_version="5.0",
        mode="read_only_contract_probe",
        trading_enabled=False,
        endpoint_invoked=False,
        historical_members=members,
        candles_parameters=parameters,
        candles_evidence=candles_evidence,
        candles_instructions=candles_instructions,
        candles_documentation=candles_documentation,
        sdk_package_evidence=sdk_package_evidence,
        official_futures_contract_evidence=official_futures_contract_evidence,
        request_evidence=request_evidence,
        config_members=config_members,
        fingerprint_sha256=digest,
    )


__all__ = [
    "HistoricalContractFingerprint",
    "HistoricalContractProbeError",
    "probe_fubon_historical_contract",
]
