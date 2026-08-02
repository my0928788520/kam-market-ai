import io
import logging
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationFailedError,
    AuthorizationSettings,
    BootstrapResult,
    CertificatePasswordMode,
    FubonCredentials,
    FailureStage,
)
from kam_market_ai.authorization.cli import main
from kam_market_ai.config import TRADING_ENABLED
from kam_market_ai.logging_config import RedactingFilter


class FakeWebSocket:
    def on(self, event: str, listener: object) -> None: pass
    def off(self, event: str, listener: object) -> None: pass
    def connect(self) -> None: raise AssertionError("bootstrap must not connect")
    def subscribe(self, params: object) -> None: raise AssertionError("bootstrap must not subscribe")
    def unsubscribe(self, params: object) -> None: raise AssertionError("bootstrap must not unsubscribe")
    def disconnect(self) -> None: raise AssertionError("bootstrap must not disconnect")


class FakeFutoptRest:
    intraday = object()
    historical = object()


class FakeStockRest:
    intraday = object()
    historical = object()


class FakeSdk:
    def __init__(
        self,
        login_success: bool = True,
        sdk_message: str = "fixture SDK message",
        login_exception: Exception | None = None,
        init_exception: Exception | None = None,
    ) -> None:
        self.login_calls = 0
        self.init_calls = 0
        self.login_success = login_success
        self.sdk_message = sdk_message
        self.login_exception = login_exception
        self.init_exception = init_exception
        self.login_argument_counts: list[int] = []
        self.marketdata = type("MarketData", (), {
            "websocket_client": type("WebSockets", (), {
                "futopt": FakeWebSocket(), "stock": FakeWebSocket(),
            })(),
            "rest_client": type("Rest", (), {
                "futopt": FakeFutoptRest(), "stock": FakeStockRest(),
            })(),
        })()

    def login(self, *args: str) -> object:
        self.login_calls += 1
        self.login_argument_counts.append(len(args))
        if self.login_exception:
            raise self.login_exception
        return type("LoginResult", (), {
            "is_success": self.login_success,
            "message": self.sdk_message,
            "data": ["fixture account object"],
        })()

    def init_realtime(self) -> None:
        self.init_calls += 1
        if self.init_exception:
            raise self.init_exception


class RecordingBootstrap:
    def __init__(self) -> None:
        self.dry_run: bool | None = None

    def run(self, settings: AuthorizationSettings, *, dry_run: bool = True) -> BootstrapResult:
        self.dry_run = dry_run
        return BootstrapResult(dry_run=dry_run, missing_fields=settings.missing_fields)


class AuthorizationBootstrapTests(unittest.TestCase):
    @staticmethod
    def complete_settings() -> AuthorizationSettings:
        return AuthorizationSettings(
            FubonCredentials("fixture-personal-id", "fixture-password", "fixture.pfx", "fixture-cert-password"),
            CertificatePasswordMode.CUSTOM,
        )

    def test_env_loading_reports_only_missing_field_names(self) -> None:
        settings = AuthorizationSettings.from_local_env("missing.env", environment={})
        self.assertEqual(settings.missing_fields, (
            "FUBON_NEO_PERSONAL_ID", "FUBON_NEO_PASSWORD", "FUBON_NEO_CERT_PATH", "FUBON_NEO_CERT_PASSWORD",
        ))
        self.assertNotIn("password", repr(settings.credentials).lower())

    def test_legacy_account_key_is_not_a_valid_personal_id(self) -> None:
        settings = AuthorizationSettings.from_local_env(
            "missing.env", environment={"FUBON_NEO_ACCOUNT": "legacy-value"}
        )
        self.assertIn("FUBON_NEO_PERSONAL_ID", settings.missing_fields)
        self.assertFalse(hasattr(settings.credentials, "account"))

    def test_dry_run_never_creates_sdk_or_connects(self) -> None:
        factory_calls = 0

        def factory() -> FakeSdk:
            nonlocal factory_calls
            factory_calls += 1
            return FakeSdk()

        result = AuthorizationBootstrap(factory).run(
            AuthorizationSettings(FubonCredentials()), dry_run=True
        )
        self.assertTrue(result.dry_run)
        self.assertEqual(factory_calls, 0)
        self.assertIsNone(result.clients)

    def test_dry_run_does_not_validate_certificate_path(self) -> None:
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", side_effect=AssertionError):
            result = AuthorizationBootstrap().run(self.complete_settings(), dry_run=True)
        self.assertTrue(result.dry_run)

    def test_live_bootstrap_returns_only_marketdata_clients(self) -> None:
        sdk = FakeSdk()
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", return_value=True):
            result = AuthorizationBootstrap(lambda: sdk).run(self.complete_settings(), dry_run=False)
        self.assertEqual((sdk.login_calls, sdk.init_calls), (1, 1))
        self.assertEqual(sdk.login_argument_counts, [4])
        self.assertFalse(result.dry_run)
        self.assertIsNotNone(result.clients)
        self.assertFalse(hasattr(result, "sdk"))
        self.assertFalse(hasattr(result, "account"))
        assert result.clients is not None
        self.assertIs(result.clients.futopt_websocket, sdk.marketdata.websocket_client.futopt)

    def test_default_mode_uses_exactly_three_login_arguments(self) -> None:
        sdk = FakeSdk()
        settings = AuthorizationSettings(
            FubonCredentials("fixture-personal-id", "fixture-password", "fixture.pfx", ""),
            CertificatePasswordMode.DEFAULT,
        )
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", return_value=True):
            result = AuthorizationBootstrap(lambda: sdk).run(settings, dry_run=False)
        self.assertIsNotNone(result.clients)
        self.assertEqual((sdk.login_calls, sdk.login_argument_counts, sdk.init_calls), (1, [3], 1))

    def test_custom_mode_requires_certificate_password(self) -> None:
        settings = AuthorizationSettings(
            FubonCredentials("fixture-personal-id", "fixture-password", "fixture.pfx", ""),
            CertificatePasswordMode.CUSTOM,
        )
        with self.assertRaises(AuthorizationFailure) as raised:
            AuthorizationBootstrap().run(settings, dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.CONFIG_ERROR)

    def test_invalid_certificate_password_mode_is_config_error(self) -> None:
        settings = AuthorizationSettings.from_local_env(
            "missing.env", environment={"FUBON_NEO_CERT_PASSWORD_MODE": "UNKNOWN"}
        )
        self.assertIsNone(settings.certificate_password_mode)
        with self.assertRaises(AuthorizationFailure) as raised:
            AuthorizationBootstrap().run(settings, dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.CONFIG_ERROR)

    def test_env_default_mode_does_not_require_certificate_password(self) -> None:
        settings = AuthorizationSettings.from_local_env("missing.env", environment={
            "FUBON_NEO_PERSONAL_ID": "fixture-personal-id",
            "FUBON_NEO_PASSWORD": "fixture-password",
            "FUBON_NEO_CERT_PATH": "fixture.pfx",
            "FUBON_NEO_CERT_PASSWORD_MODE": "DEFAULT",
        })
        self.assertEqual(settings.certificate_password_mode, CertificatePasswordMode.DEFAULT)
        self.assertEqual(settings.missing_fields, ())

    def test_failed_login_hard_gate_never_starts_realtime_or_exposes_sdk_values(self) -> None:
        sdk = FakeSdk(login_success=False, sdk_message="fixture internal failure")
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", return_value=True):
            with self.assertRaises(AuthorizationFailedError) as raised:
                AuthorizationBootstrap(lambda: sdk).run(self.complete_settings(), dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.LOGIN_REJECTED)
        self.assertEqual((sdk.login_calls, sdk.init_calls), (1, 0))
        self.assertEqual(sdk.login_argument_counts, [4])
        for forbidden in ("fixture internal failure", "fixture-personal-id", "fixture-password", "fixture.pfx"):
            self.assertNotIn(forbidden, str(raised.exception))

    def test_missing_settings_is_config_error(self) -> None:
        with self.assertRaises(AuthorizationFailure) as raised:
            AuthorizationBootstrap().run(AuthorizationSettings(FubonCredentials()), dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.CONFIG_ERROR)

    def test_missing_certificate_is_cert_not_found_without_creating_sdk(self) -> None:
        factory_calls = 0

        def factory() -> FakeSdk:
            nonlocal factory_calls
            factory_calls += 1
            return FakeSdk()

        with self.assertRaises(AuthorizationFailure) as raised:
            AuthorizationBootstrap(factory).run(self.complete_settings(), dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.CERT_NOT_FOUND)
        self.assertEqual(factory_calls, 0)

    def test_invalid_certificate_path_is_classified_without_reading_contents(self) -> None:
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", side_effect=OSError("fixture path error")):
            with self.assertRaises(AuthorizationFailure) as raised:
                AuthorizationBootstrap().run(self.complete_settings(), dry_run=False)
        self.assertEqual(raised.exception.stage, FailureStage.CERT_PATH_INVALID)
        self.assertNotIn("fixture path error", str(raised.exception))

    def test_sdk_factory_and_login_exceptions_are_safely_classified(self) -> None:
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", return_value=True):
            with self.assertRaises(AuthorizationFailure) as factory_error:
                AuthorizationBootstrap(lambda: (_ for _ in ()).throw(RuntimeError("fixture sdk error"))).run(
                    self.complete_settings(), dry_run=False
                )
            with self.assertRaises(AuthorizationFailure) as login_error:
                AuthorizationBootstrap(lambda: FakeSdk(login_exception=RuntimeError("fixture login error"))).run(
                    self.complete_settings(), dry_run=False
                )
        self.assertEqual(factory_error.exception.stage, FailureStage.SDK_INIT_ERROR)
        self.assertEqual(login_error.exception.stage, FailureStage.LOGIN_EXCEPTION)
        self.assertNotIn("fixture sdk error", str(factory_error.exception))
        self.assertNotIn("fixture login error", str(login_error.exception))

    def test_realtime_initialization_exception_is_sdk_init_error(self) -> None:
        with patch("kam_market_ai.authorization.bootstrap.Path.is_file", return_value=True):
            with self.assertRaises(AuthorizationFailure) as raised:
                AuthorizationBootstrap(lambda: FakeSdk(init_exception=RuntimeError("fixture realtime error"))).run(
                    self.complete_settings(), dry_run=False
                )
        self.assertEqual(raised.exception.stage, FailureStage.SDK_INIT_ERROR)
        self.assertNotIn("fixture realtime error", str(raised.exception))

    def test_cli_defaults_to_dry_run(self) -> None:
        bootstrap = RecordingBootstrap()
        with redirect_stdout(io.StringIO()):
            status = main(["--env", "missing.env"], bootstrap=bootstrap)  # type: ignore[arg-type]
        self.assertEqual(status, 0)
        self.assertIs(bootstrap.dry_run, True)

    def test_cli_failure_prints_only_stage_code(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["--live", "--env", "missing.env"])
        self.assertEqual(status, 2)
        self.assertEqual(output.getvalue().strip(), "failure_stage=CONFIG_ERROR")

    def test_redacting_filter_hides_fubon_values_and_trading_stays_disabled(self) -> None:
        record = logging.LogRecord(
            "test", logging.INFO, "", 0,
            "FUBON_NEO_PERSONAL_ID=fixture-personal-id FUBON_NEO_PASSWORD=fixture-password "
            "FUBON_NEO_CERT_PATH=fixture.pfx FUBON_NEO_CERT_PASSWORD=fixture-cert-password",
            (), None,
        )
        RedactingFilter().filter(record)
        self.assertNotIn("fixture-personal-id", record.msg)
        self.assertNotIn("fixture-password", record.msg)
        self.assertNotIn("fixture.pfx", record.msg)
        self.assertIs(TRADING_ENABLED, False)


if __name__ == "__main__":
    unittest.main()
