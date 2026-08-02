"""Local authorization bootstrap for Fubon market-data clients only.

This module is the sole place where a live FubonSDK can exist. It returns only
AuthorizedMarketDataClients and never exposes an SDK, login result, or account.
"""

from __future__ import annotations

import getpass
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from kam_market_ai.config import load_dotenv_values
from kam_market_ai.market_data import AuthorizedMarketDataClients


_REQUIRED_FIELDS = (
    "FUBON_NEO_PERSONAL_ID",
    "FUBON_NEO_PASSWORD",
    "FUBON_NEO_CERT_PATH",
    "FUBON_NEO_CERT_PASSWORD",
)


class FailureStage(StrEnum):
    CONFIG_ERROR = "CONFIG_ERROR"
    CERT_PATH_INVALID = "CERT_PATH_INVALID"
    CERT_NOT_FOUND = "CERT_NOT_FOUND"
    SDK_INIT_ERROR = "SDK_INIT_ERROR"
    LOGIN_EXCEPTION = "LOGIN_EXCEPTION"
    LOGIN_REJECTED = "LOGIN_REJECTED"


class CertificatePasswordMode(StrEnum):
    DEFAULT = "DEFAULT"
    CUSTOM = "CUSTOM"


class AuthorizationFailure(RuntimeError):
    """A non-sensitive authorization failure intended for CLI display."""

    def __init__(self, stage: FailureStage) -> None:
        self.stage = stage
        super().__init__(stage.value)


class AuthorizationConfigurationError(AuthorizationFailure):
    """Raised before live login when local configuration is unusable."""

    def __init__(self) -> None:
        super().__init__(FailureStage.CONFIG_ERROR)


class AuthorizationFailedError(AuthorizationFailure):
    """Safe generic failure; never expose SDK messages or account data."""

    def __init__(self) -> None:
        super().__init__(FailureStage.LOGIN_REJECTED)


class SdkFactory(Protocol):
    def __call__(self) -> Any: ...


@dataclass(frozen=True, slots=True, repr=False)
class FubonCredentials:
    personal_id: str = ""
    password: str = ""
    certificate_path: str = ""
    certificate_password: str = ""

    def missing_fields(self, *, require_certificate_password: bool) -> tuple[str, ...]:
        fields = _REQUIRED_FIELDS if require_certificate_password else _REQUIRED_FIELDS[:-1]
        values = (self.personal_id, self.password, self.certificate_path, self.certificate_password)
        if not require_certificate_password:
            values = values[:-1]
        return tuple(name for name, value in zip(fields, values, strict=True) if not value.strip())

    def __repr__(self) -> str:
        return "FubonCredentials(REDACTED)"


@dataclass(frozen=True, slots=True)
class AuthorizationSettings:
    credentials: FubonCredentials
    certificate_password_mode: CertificatePasswordMode | None = CertificatePasswordMode.CUSTOM

    @classmethod
    def from_local_env(
        cls,
        env_path: str | Path = ".env",
        environment: Mapping[str, str] | None = None,
    ) -> "AuthorizationSettings":
        try:
            local = load_dotenv_values(env_path)
        except (OSError, UnicodeError):
            raise AuthorizationConfigurationError() from None
        merged = {**local, **dict(os.environ if environment is None else environment)}
        raw_mode = merged.get("FUBON_NEO_CERT_PASSWORD_MODE", "CUSTOM").strip().upper()
        try:
            mode: CertificatePasswordMode | None = CertificatePasswordMode(raw_mode)
        except ValueError:
            mode = None
        return cls(
            FubonCredentials(
                personal_id=merged.get("FUBON_NEO_PERSONAL_ID", ""),
                password=merged.get("FUBON_NEO_PASSWORD", ""),
                certificate_path=merged.get("FUBON_NEO_CERT_PATH", ""),
                certificate_password=merged.get("FUBON_NEO_CERT_PASSWORD", ""),
            ),
            certificate_password_mode=mode,
        )

    @classmethod
    def from_interactive_prompt(cls) -> "AuthorizationSettings":
        """Explicit local terminal prompts; never called by default CLI dry-run."""
        raw_mode = input("Certificate password mode [CUSTOM/DEFAULT]: ").strip().upper() or "CUSTOM"
        try:
            mode: CertificatePasswordMode | None = CertificatePasswordMode(raw_mode)
        except ValueError:
            mode = None
        return cls(
            FubonCredentials(
                personal_id=getpass.getpass("Fubon personal ID: ").strip(),
                password=getpass.getpass("Fubon password: "),
                certificate_path=getpass.getpass("Certificate path: ").strip(),
                certificate_password=getpass.getpass("Certificate password: "),
            ),
            certificate_password_mode=mode,
        )

    @property
    def missing_fields(self) -> tuple[str, ...]:
        if self.certificate_password_mode is None:
            return ("FUBON_NEO_CERT_PASSWORD_MODE",)
        return self.credentials.missing_fields(
            require_certificate_password=self.certificate_password_mode is CertificatePasswordMode.CUSTOM
        )


@dataclass(frozen=True, slots=True, repr=False)
class BootstrapResult:
    dry_run: bool
    missing_fields: tuple[str, ...]
    clients: AuthorizedMarketDataClients | None = None

    def __repr__(self) -> str:
        return (
            "BootstrapResult("
            f"dry_run={self.dry_run}, missing_fields={self.missing_fields}, "
            f"clients_present={self.clients is not None})"
        )


def _default_sdk_factory() -> Any:
    # Deliberately lazy: dry-run never imports or constructs an SDK instance.
    from fubon_neo.sdk import FubonSDK

    return FubonSDK()


class AuthorizationBootstrap:
    """Converts an authorized local SDK session into market-data clients only."""

    def __init__(self, sdk_factory: SdkFactory = _default_sdk_factory) -> None:
        self._sdk_factory = sdk_factory

    @staticmethod
    def _validate_certificate_path(certificate_path: str) -> None:
        try:
            path = Path(certificate_path)
            exists = path.is_file()
        except (OSError, ValueError):
            raise AuthorizationFailure(FailureStage.CERT_PATH_INVALID) from None
        if not exists:
            raise AuthorizationFailure(FailureStage.CERT_NOT_FOUND)

    def run(self, settings: AuthorizationSettings, *, dry_run: bool = True) -> BootstrapResult:
        missing = settings.missing_fields
        if settings.certificate_password_mode is None:
            raise AuthorizationConfigurationError()
        if dry_run:
            return BootstrapResult(dry_run=True, missing_fields=missing)
        if missing:
            raise AuthorizationConfigurationError()
        self._validate_certificate_path(settings.credentials.certificate_path)
        try:
            sdk = self._sdk_factory()
        except Exception:
            raise AuthorizationFailure(FailureStage.SDK_INIT_ERROR) from None
        # The login return value may contain account objects. It remains local and
        # is deliberately discarded before any KAM object is created.
        try:
            if settings.certificate_password_mode is CertificatePasswordMode.DEFAULT:
                login_result = sdk.login(
                    settings.credentials.personal_id,
                    settings.credentials.password,
                    settings.credentials.certificate_path,
                )
            else:
                login_result = sdk.login(
                    settings.credentials.personal_id,
                    settings.credentials.password,
                    settings.credentials.certificate_path,
                    settings.credentials.certificate_password,
                )
        except Exception:
            raise AuthorizationFailure(FailureStage.LOGIN_EXCEPTION) from None
        try:
            login_success = getattr(login_result, "is_success", False)
        except Exception:
            raise AuthorizationFailure(FailureStage.LOGIN_EXCEPTION) from None
        if login_success is not True:
            raise AuthorizationFailedError()
        del login_result
        try:
            sdk.init_realtime()
            marketdata = sdk.marketdata
            clients = AuthorizedMarketDataClients(
                futopt_websocket=marketdata.websocket_client.futopt,
                futopt_rest=marketdata.rest_client.futopt,
                stock_websocket=marketdata.websocket_client.stock,
                stock_rest=marketdata.rest_client.stock,
            )
        except Exception:
            raise AuthorizationFailure(FailureStage.SDK_INIT_ERROR) from None
        return BootstrapResult(dry_run=False, missing_fields=(), clients=clients)
