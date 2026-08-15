"""Local, read-only live five-timeframe dashboard service."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from wsgiref.simple_server import make_server

from kam_market_ai.authorization.bootstrap import (
    AuthorizationBootstrap,
    AuthorizationFailure,
    AuthorizationSettings,
)
from kam_market_ai.config import Settings, UnsafeConfigurationError, load_dotenv_values
from kam_market_ai.dashboard.app import DashboardApp
from kam_market_ai.live_read_only.five_timeframe_operator_view import (
    build_five_timeframe_operator_view,
)
from kam_market_ai.live_read_only.five_timeframe_snapshot import (
    read_five_timeframe_snapshot,
    write_five_timeframe_snapshot,
)
from kam_market_ai.models import Candle, Instrument
from kam_market_ai.notifications import (
    LinePushNotifier,
    build_due_tmf_rollover_alert,
    build_paper_exit_alert,
    build_pending_order_alert,
)
from kam_market_ai.paper_trading.live_tmf_simulation import (
    LiveTmfPaperSimulation,
    TmfPaperJournalStore,
    TmfPaperSimulationConfig,
)
from kam_market_ai.paper_trading.operator_app import create_operator_app

from .fubon_five_timeframe_pipeline import FiveTimeframe, FubonFiveTimeframeCandlePipeline
from .fubon_live_chart_source import (
    FubonLiveChartSource,
    FubonLiveDashboardMarketSource,
    FubonLiveQuoteSource,
)
from .fubon_live_five_timeframe_verifier import FubonLiveFiveTimeframeVerifier
from .fubon_neo import (
    FubonIntradayCandlesAdapter,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)
from .fubon_tmf_contract_probe import FubonTmfContractProbe
from .index_futures_product import index_futures_product, infer_index_futures_instrument
from .taifex_official_history import TaifexOfficialHistorySource


@dataclass(frozen=True, slots=True)
class RefreshHealth:
    successful_refreshes: int
    consecutive_failures: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    status: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "successful_refreshes": self.successful_refreshes,
            "consecutive_failures": self.consecutive_failures,
            "last_success_at": self.last_success_at.isoformat() if self.last_success_at else None,
            "last_failure_at": self.last_failure_at.isoformat() if self.last_failure_at else None,
            "status": self.status,
        }


class LiveFiveTimeframeSnapshotRefresher:
    def __init__(
        self,
        verifier: FubonLiveFiveTimeframeVerifier,
        *,
        symbol: str,
        session: str | None,
        after_hours: bool,
        snapshot_path: str | Path,
        on_success: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(verifier, FubonLiveFiveTimeframeVerifier):
            raise TypeError("FubonLiveFiveTimeframeVerifier is required")
        self.verifier = verifier
        self.symbol = symbol
        self.session = session
        self.after_hours = after_hours
        self.snapshot_path = Path(snapshot_path)
        self.on_success = on_success
        self._successful_refreshes = 0
        self._consecutive_failures = 0
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._lock = threading.RLock()

    def set_session(self, *, after_hours: bool) -> None:
        with self._lock:
            self.after_hours = bool(after_hours)
            self.session = "afterhours" if after_hours else None

    @property
    def health(self) -> RefreshHealth:
        return RefreshHealth(
            self._successful_refreshes,
            self._consecutive_failures,
            self._last_success_at,
            self._last_failure_at,
            "READY" if self._consecutive_failures == 0 and self._last_success_at else "DEGRADED",
        )

    def refresh_once(self) -> dict[str, object]:
        with self._lock:
            payload = self.verifier.run(
                symbol=self.symbol,
                session=self.session,
                after_hours=self.after_hours,
            )
            write_five_timeframe_snapshot(self.snapshot_path, payload)
            if self.on_success is not None:
                self.on_success()
            self._successful_refreshes += 1
            self._consecutive_failures = 0
            self._last_success_at = datetime.now(UTC)
            return payload

    def refresh_safely(self) -> bool:
        """Retry on the next cycle without replacing the last verified snapshot."""
        try:
            self.refresh_once()
        except Exception:  # noqa: BLE001
            self._consecutive_failures += 1
            self._last_failure_at = datetime.now(UTC)
            return False
        return True


def build_local_dashboard_router(operator_app: Any, diagnostic_app: Any) -> Any:
    """Keep the canonical operator UI and its assets on their original routes."""
    diagnostic_paths = {
        "/five-timeframe",
        "/api/five-timeframe",
        "/api/five-timeframe/health",
        "/static/dashboard.css",
    }

    def application(environ: Any, start_response: Any) -> Any:
        if str(environ.get("PATH_INFO", "/")) in diagnostic_paths:
            return diagnostic_app(environ, start_response)
        return operator_app(environ, start_response)

    return application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KAM 富邦 TX／MTX／TMF 本機五週期唯讀儀表板")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--symbol", help="省略時以已驗證成交量自動解析活動 TMF 契約")
    parser.add_argument("--instrument", choices=("TX", "MTX", "TMF"), help="商品；提供 symbol 時可自動辨識")
    parser.add_argument("--session", default=None)
    parser.add_argument("--after-hours", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--refresh-seconds", type=int, default=3)
    parser.add_argument("--snapshot", default="debug/five_timeframe/live.json")
    parser.add_argument("--chart-history", default="debug/five_timeframe/tmf_60m_history.json")
    parser.add_argument("--chart-history-15m", default="debug/five_timeframe/tmf_15m_history.json")
    parser.add_argument(
        "--taifex-history-cache",
        default="debug/five_timeframe/taifex_official_history.json",
        help="TAIFEX 官方已收盤歷史資料的本機雜湊快取",
    )
    parser.add_argument(
        "--paper-test-armed",
        action="store_true",
        help="人工授權本次工作階段自動留下 Paper Trading 紀錄；不啟用真實下單",
    )
    parser.add_argument(
        "--paper-journal",
        default="debug/paper_trading/tmf_live_journal.json",
    )
    parser.add_argument(
        "--line-alerts",
        action="store_true",
        help="將新的 Paper Trading 進場提案推播至 LINE；不送出真實委託",
    )
    parser.add_argument(
        "--line-alert-state",
        default="debug/notifications/tmf_line_delivery.json",
        help="不含密鑰的 LINE 傳送去重與重試狀態",
    )
    parser.add_argument("--open-browser", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    bootstrap: AuthorizationBootstrap | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if not args.live:
        print(json.dumps({"success": False, "failure_stage": "LIVE_FLAG_REQUIRED"}))
        return 2
    if args.host not in {"127.0.0.1", "localhost"} or args.port <= 0 or args.refresh_seconds < 3:
        print(json.dumps({"success": False, "failure_stage": "LOCAL_SERVICE_INPUT_ERROR"}))
        return 2
    try:
        Settings.load(args.env)
        result = (bootstrap or AuthorizationBootstrap()).run(
            AuthorizationSettings.from_local_env(args.env),
            dry_run=False,
        )
    except (AuthorizationFailure, UnsafeConfigurationError, ValueError):
        print(json.dumps({"success": False, "failure_stage": "AUTHORIZATION_ERROR"}))
        return 2
    if result.clients is None:
        print(json.dumps({"success": False, "failure_stage": "MARKET_CLIENTS_UNAVAILABLE"}))
        return 2
    try:
        if args.symbol:
            symbol = args.symbol
            instrument = infer_index_futures_instrument(symbol)
            if args.instrument is not None and Instrument(args.instrument) is not instrument:
                raise ValueError("instrument and symbol identity mismatch")
            contract_month = None
        else:
            instrument = Instrument(args.instrument or "TMF")
            if instrument is not Instrument.TMF:
                raise ValueError("TX and MTX currently require an explicit verified symbol")
            active_contract = FubonTmfContractProbe(result.clients).resolve_active(
                after_hours=args.after_hours,
            )
            symbol = active_contract.symbol
            contract_month = active_contract.end_date.strftime("%Y%m")
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "ACTIVE_CONTRACT_RESOLUTION_ERROR"}))
        return 1

    product_slug = instrument.value.lower()
    if args.snapshot == "debug/five_timeframe/live.json":
        args.snapshot = f"debug/five_timeframe/{product_slug}_live.json"
    if args.chart_history == "debug/five_timeframe/tmf_60m_history.json":
        args.chart_history = f"debug/five_timeframe/{product_slug}_60m_history.json"
    if args.chart_history_15m == "debug/five_timeframe/tmf_15m_history.json":
        args.chart_history_15m = f"debug/five_timeframe/{product_slug}_15m_history.json"
    if args.paper_journal == "debug/paper_trading/tmf_live_journal.json":
        args.paper_journal = f"debug/paper_trading/{product_slug}_live_journal.json"

    resolver = VerifiedContractResolver((
        ResolvedFuturesContract(instrument, symbol, False),
        ResolvedFuturesContract(instrument, symbol, True),
    ))
    pipeline = FubonFiveTimeframeCandlePipeline(
        FubonIntradayCandlesAdapter(result.clients, resolver),
    )
    official_history_source = TaifexOfficialHistorySource(args.taifex_history_cache)
    verifier = FubonLiveFiveTimeframeVerifier(
        pipeline,
        official_history_source if instrument is Instrument.TMF else None,
        instrument=instrument,
    )
    quote_source = FubonLiveQuoteSource(
        result.clients,
        symbol=symbol,
        instrument=instrument,
        after_hours=args.after_hours,
    )
    dashboard_market_source = FubonLiveDashboardMarketSource(
        quote_source,
        symbol=symbol,
        instrument=instrument,
        contract_month=contract_month,
        after_hours=args.after_hours,
    )

    def closed_higher_timeframes() -> dict[FiveTimeframe, tuple[Candle, ...]]:
        """Chart-only closed history; never upgrades after-hours KAM readiness."""
        official = official_history_source.fetch(
            observed_at=datetime.now(UTC),
            after_hours=False,
        )
        return {
            FiveTimeframe.DAY: official.higher_timeframes.day_candles,
            FiveTimeframe.WEEK: official.higher_timeframes.week_candles,
        }

    chart_source = FubonLiveChartSource(
        lambda: verifier.latest_candle_result,
        current_price_provider=lambda: quote_source.latest,
        closed_higher_timeframe_provider=(closed_higher_timeframes if instrument is Instrument.TMF else None),
        after_hours=args.after_hours,
        history_path=args.chart_history,
        history_15m_path=args.chart_history_15m,
        instrument=instrument,
    )

    paper_session: LiveTmfPaperSimulation | None = None
    line_notifier: LinePushNotifier | None = None
    active_line_alert = None
    active_line_alert_is_exit = False
    paper_runtime: dict[str, object] = {"armed": False, "action": "DISARMED"}
    if args.line_alerts:
        if not args.paper_test_armed:
            print(json.dumps({"success": False, "failure_stage": "LINE_ALERTS_REQUIRE_PAPER_MODE"}))
            return 2
        local_env = load_dotenv_values(args.env)
        try:
            line_notifier = LinePushNotifier(
                local_env.get("KAM_LINE_CHANNEL_ACCESS_TOKEN", ""),
                local_env.get("KAM_LINE_RECIPIENT_USER_ID", ""),
                state_path=args.line_alert_state,
            )
        except ValueError:
            print(json.dumps({"success": False, "failure_stage": "LINE_ALERT_CONFIGURATION_ERROR"}))
            return 2
    if args.paper_test_armed:
        try:
            product = index_futures_product(instrument)
            paper_config = TmfPaperSimulationConfig(
                instrument=symbol,
                point_value=product.point_value,
                initial_margin=product.initial_margin,
                maintenance_margin=product.maintenance_margin,
                paper_trading_enabled=True,
                manual_approval_granted=True,
            )
            paper_store = TmfPaperJournalStore(args.paper_journal)
            paper_journal = paper_store.load(paper_config)
            paper_store.save(paper_journal)
            paper_session = LiveTmfPaperSimulation(
                paper_config,
                journal=paper_journal,
                store=paper_store,
            )
            paper_runtime = {
                "armed": True,
                "action": "WAITING_FOR_KAM",
                "line_alert_status": (
                    "ARMED_WAITING_FOR_PAPER_PROPOSAL" if line_notifier is not None else "DISABLED"
                ),
                "direction": "HOLD",
                "reason_codes": ["KAM_CONDITION_NOT_MET"],
                "cash_balance": str(paper_journal.ledger.cash_balance),
                "open_positions": len(paper_journal.ledger.positions),
                "journal_hash": paper_journal.journal_hash,
                "proposal_hash": None,
                "fill_hashes": [],
                "margin_state": paper_journal.margin_state_payload(),
                "performance_summary": paper_journal.performance_summary_payload(),
                "performance_event": (
                    paper_journal.events[-1].canonical_payload()
                    if paper_journal.events
                    else None
                ),
                "live_order_allowed": False,
                "broker_connected": False,
                "execution_boundary": {
                    "mode": "paper_only",
                    "automatic_paper_execution": True,
                    "real_order_requires_human_action": True,
                    "broker_submission_available": False,
                    "live_order_allowed": False,
                },
            }
        except (OSError, TypeError, ValueError):
            print(json.dumps({"success": False, "failure_stage": "PAPER_JOURNAL_ERROR"}))
            return 2

    def capture_verified_refresh() -> None:
        nonlocal active_line_alert, active_line_alert_is_exit
        quote_source.refresh_safely()
        chart_source.capture_latest()
        if line_notifier is not None:
            rollover_alert = build_due_tmf_rollover_alert(datetime.now(UTC), symbol=symbol)
            if rollover_alert is not None:
                try:
                    if line_notifier.send_once(rollover_alert):
                        paper_runtime["line_alert_status"] = "ROLLOVER_SENT"
                except (OSError, RuntimeError, TimeoutError):
                    paper_runtime["line_alert_status"] = "RETRY_PENDING"
        if paper_session is None or verifier.latest_candle_result is None:
            return
        try:
            result = paper_session.process_candles(
                verifier.latest_candle_result,
                evaluated_at=datetime.now(UTC),
            )
            safe_result = result.safe_payload()
            paper_runtime.update(safe_result)
            paper_runtime["armed"] = True
            if line_notifier is not None:
                exit_alert = build_paper_exit_alert(safe_result)
                entry_alert = build_pending_order_alert(safe_result)
                if exit_alert is not None:
                    active_line_alert = exit_alert
                    active_line_alert_is_exit = True
                elif entry_alert is not None:
                    active_line_alert = entry_alert
                    active_line_alert_is_exit = False
                if active_line_alert is not None:
                    try:
                        if active_line_alert_is_exit:
                            sent = line_notifier.send_once(active_line_alert)
                            paper_runtime["line_alert_status"] = (
                                "EXIT_SENT" if sent else "WAITING_OR_DUPLICATE"
                            )
                            if sent:
                                active_line_alert = None
                                active_line_alert_is_exit = False
                        else:
                            sent = line_notifier.send_due(active_line_alert, datetime.now(UTC))
                            paper_runtime["line_alert_status"] = (
                                "SENT" if sent else "WAITING_OR_DUPLICATE"
                            )
                    except (OSError, RuntimeError, TimeoutError):
                        paper_runtime["line_alert_status"] = "RETRY_PENDING"
        except (OSError, TypeError, ValueError):
            # A paper-journal failure must never replace the last verified market snapshot.
            return

    refresher = LiveFiveTimeframeSnapshotRefresher(
        verifier,
        symbol=symbol,
        session=args.session,
        after_hours=args.after_hours,
        snapshot_path=args.snapshot,
        on_success=capture_verified_refresh,
    )

    session_switch_lock = threading.Lock()

    def switch_session(requested: str) -> tuple[bool, str]:
        if requested not in {"regular", "afterhours"}:
            return False, "時段參數無效"
        target_after_hours = requested == "afterhours"
        with session_switch_lock:
            previous = refresher.after_hours
            if previous == target_after_hours:
                return True, "已是日盤" if not previous else "已是夜盤"
            paper_runtime.update({
                "armed": False,
                "action": "SWITCHING_SESSION",
                "direction": "HOLD",
                "reason_codes": ["SESSION_SWITCH_IN_PROGRESS"],
            })
            quote_source.set_after_hours(target_after_hours)
            dashboard_market_source.set_after_hours(target_after_hours)
            chart_source.set_after_hours(target_after_hours)
            refresher.set_session(after_hours=target_after_hours)
            if refresher.refresh_safely():
                paper_runtime["armed"] = bool(args.paper_test_armed)
                paper_runtime["action"] = "WAITING_FOR_KAM"
                paper_runtime["reason_codes"] = ["KAM_CONDITION_NOT_MET"]
                return True, "已切換夜盤" if target_after_hours else "已切換日盤"
            quote_source.set_after_hours(previous)
            dashboard_market_source.set_after_hours(previous)
            chart_source.set_after_hours(previous)
            refresher.set_session(after_hours=previous)
            refresher.refresh_safely()
            paper_runtime["action"] = "SESSION_SWITCH_FAILED"
            paper_runtime["reason_codes"] = ["SESSION_DATA_VERIFICATION_FAILED"]
            return False, "新時段資料驗證失敗，已維持原時段"
    print(
        json.dumps(
            {
                "status": "INITIALIZING_OFFICIAL_HISTORY",
                "message": "首次建立 TAIFEX 官方歷史快取可能需要 30 至 90 秒；請保持視窗開啟。",
                "cache": args.taifex_history_cache,
                "trading_enabled": False,
                "live_order_allowed": False,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        refresher.refresh_once()
    except Exception:  # noqa: BLE001
        print(json.dumps({"success": False, "failure_stage": "INITIAL_REFRESH_ERROR"}))
        return 1

    stop = threading.Event()

    def refresh_loop() -> None:
        delay = args.refresh_seconds
        while not stop.wait(delay):
            success = refresher.refresh_safely()
            delay = (
                args.refresh_seconds
                if success
                else min(
                    60, args.refresh_seconds * (2 ** min(refresher.health.consecutive_failures, 5))
                )
            )

    worker = threading.Thread(target=refresh_loop, name="kam-five-timeframe-refresh", daemon=True)
    worker.start()
    print(
        json.dumps(
            {
                "success": True,
                "mode": "local_read_only_five_timeframe_dashboard",
                "url": f"http://{args.host}:{args.port}/",
                "api_url": f"http://{args.host}:{args.port}/api/five-timeframe",
                "health_url": f"http://{args.host}:{args.port}/api/five-timeframe/health",
                "refresh_seconds": args.refresh_seconds,
                "symbol": symbol,
                "instrument": instrument.value,
                "live_quote_source": "FUBON_INTRADAY_QUOTE",
                "live_quote_refresh_seconds": args.refresh_seconds,
                "main_dashboard_live_quote_enabled": True,
                "taifex_official_history_chart_enabled": True,
                "taifex_official_history_kam_enabled": True,
                "taifex_official_history_session": "regular",
                "night_session_history_warmup_enabled": args.after_hours,
                "forming_day_week_chart_only": True,
                "taifex_history_cache": args.taifex_history_cache,
                "paper_simulation_enabled": args.paper_test_armed,
                "paper_manual_approval_granted": args.paper_test_armed,
                "line_alerts_enabled": line_notifier is not None,
                "line_alert_mode": "paper_proposal_only" if line_notifier is not None else None,
                "line_rollover_reminders_enabled": line_notifier is not None,
                "line_alert_state": args.line_alert_state if line_notifier is not None else None,
                "paper_journal": args.paper_journal if args.paper_test_armed else None,
                "paper_stop_loss_points": 20 if args.paper_test_armed else None,
                "paper_take_profit_points": 40 if args.paper_test_armed else None,
                "paper_trend_hold_enabled": bool(args.paper_test_armed),
                "paper_take_profit_extension_points": 20 if args.paper_test_armed else None,
                "paper_point_value": int(index_futures_product(instrument).point_value) if args.paper_test_armed else None,
                "paper_margin_model": "RESERVE_RELEASE_V1" if args.paper_test_armed else None,
                "paper_initial_margin": int(index_futures_product(instrument).initial_margin) if args.paper_test_armed else None,
                "paper_maintenance_margin": int(index_futures_product(instrument).maintenance_margin) if args.paper_test_armed else None,
                "paper_margin_effective_at": (
                    "2026-08-12T05:45:00Z" if args.paper_test_armed else None
                ),
                "paper_margin_source": (
                    "TAIFEX_INDEX_MARGIN_2026-08-12" if args.paper_test_armed else None
                ),
                "trading_enabled": False,
                "live_order_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    try:
        diagnostic_app = DashboardApp(
            five_timeframe_snapshot_path=args.snapshot,
            five_timeframe_max_age_seconds=max(180, args.refresh_seconds * 3),
            five_timeframe_health_provider=lambda: refresher.health.safe_payload(),
        )
        operator_app = create_operator_app(
            lambda: build_five_timeframe_operator_view(
                read_five_timeframe_snapshot(args.snapshot), paper_runtime
            ),
            market_data_source=dashboard_market_source,
            chart_data_source=chart_source,
            session_switcher=switch_session,
        )

        application = build_local_dashboard_router(operator_app, diagnostic_app)

        with make_server(
            args.host,
            args.port,
            application,
        ) as server:
            if args.open_browser:
                webbrowser.open(f"http://{args.host}:{args.port}/")
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        worker.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LiveFiveTimeframeSnapshotRefresher",
    "RefreshHealth",
    "build_local_dashboard_router",
    "build_parser",
    "main",
]
