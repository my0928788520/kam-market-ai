from datetime import UTC, datetime, timedelta
from json import loads
from pathlib import Path

from kam_market_ai.notifications.line_pending_order import (
    LinePushNotifier,
    PersistentRefreshFaultMonitor,
    build_paper_exit_alert,
    build_paper_health_alert,
    build_paper_sample_milestone_alert,
    build_pending_order_alert,
)


def payload():
    return {
        "action": "entry_filled",
        "direction": "LONG",
        "proposal_hash": "a" * 64,
        "live_order_allowed": False,
        "execution_boundary": {"broker_submission_available": False},
        "performance_event": {
            "instrument": "TMFH6",
            "quantity": "1",
            "entry_price": "22000",
            "stop_loss_price": "21980",
            "take_profit_price": "22040",
            "observed_at": "2026-08-17T01:00:00Z",
        },
    }


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_alert_contains_only_review_fields_and_expires_in_fifteen_minutes() -> None:
    alert = build_pending_order_alert(payload())
    assert alert is not None
    assert alert.expires_at == datetime(2026, 8, 17, 1, 15, tzinfo=UTC)
    assert "方向：做多" in alert.text and "TMFH6" in alert.text
    assert "口數：固定 1 口微台" in alert.text
    assert "建議進場：22000" in alert.text
    assert "停損：21980" in alert.text and "第一停利：22040" in alert.text
    assert "延伸停利：22060" in alert.text
    assert "15分20MA條件失效" in alert.text
    assert "Paper Trading" in alert.text and "不會送出真實委託" in alert.text
    for forbidden in ("account", "password", "token", "certificate"):
        assert forbidden not in alert.text.lower()


def test_non_entry_or_live_capable_payload_never_builds_an_alert() -> None:
    value = payload()
    value["action"] = "hold"
    assert build_pending_order_alert(value) is None


def test_short_alert_has_one_contract_and_descending_exit_prices() -> None:
    value = payload()
    value["direction"] = "SHORT"
    value["performance_event"].update(
        {
            "stop_loss_price": "22020",
            "take_profit_price": "21960",
        }
    )

    alert = build_pending_order_alert(value)

    assert alert is not None
    assert "方向：做空" in alert.text
    assert "第一停利：21960" in alert.text
    assert "延伸停利：21940" in alert.text


def test_entry_alert_rejects_more_than_one_micro_contract() -> None:
    value = payload()
    value["performance_event"]["quantity"] = "2"

    assert build_pending_order_alert(value) is None
    value = payload()
    value["live_order_allowed"] = True
    assert build_pending_order_alert(value) is None


def test_line_push_is_deduplicated_without_logging_secrets() -> None:
    captured = {}

    def opener(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    notifier = LinePushNotifier("secret-token", "U-recipient", opener=opener)
    alert = build_pending_order_alert(payload())
    assert alert is not None
    assert notifier.send_once(alert) is True
    assert notifier.send_once(alert) is False
    assert captured["payload"]["to"] == "U-recipient"
    assert captured["timeout"] == 5
    assert "secret-token" not in repr(notifier)


def test_three_stage_reminders_send_only_the_latest_due_stage() -> None:
    messages = []

    def opener(request, timeout):
        messages.append(loads(request.data.decode("utf-8"))["messages"][0]["text"])
        return Response()

    notifier = LinePushNotifier("secret-token", "U-recipient", opener=opener)
    alert = build_pending_order_alert(payload())
    assert alert is not None
    created = alert.expires_at - timedelta(minutes=15)
    assert notifier.send_due(alert, created) is True
    assert notifier.send_due(alert, created + timedelta(minutes=1)) is False
    assert notifier.send_due(alert, created + timedelta(minutes=3)) is True
    assert notifier.send_due(alert, created + timedelta(minutes=14)) is True
    assert notifier.send_due(alert, alert.expires_at) is False
    assert len(messages) == 3
    assert messages[1].startswith("KAM 再次提醒")
    assert messages[2].startswith("KAM 委託建議即將失效")


def test_wake_up_near_expiry_sends_only_one_latest_reminder() -> None:
    calls = []
    notifier = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
    )
    alert = build_pending_order_alert(payload())
    assert alert is not None
    assert notifier.send_due(alert, alert.expires_at - timedelta(minutes=1)) is True
    assert notifier.send_due(alert, alert.expires_at - timedelta(seconds=30)) is False
    assert len(calls) == 1


def test_stop_loss_exit_builds_one_paper_close_alert() -> None:
    value = payload()
    value["action"] = "exit_filled"
    value["performance_event"].update(
        {
            "event_type": "stop_loss_exit",
            "current_price": "21978",
            "realized_pnl": "-220",
            "fill_hash": "f" * 64,
            "proposal_hash": "a" * 64,
        }
    )

    alert = build_paper_exit_alert(value)

    assert alert is not None
    assert "模擬停損平倉" in alert.text
    assert "已實現損益：-220" in alert.text
    assert "舊提醒已停止" in alert.text
    assert alert.live_order_allowed is False


def test_take_profit_exit_is_deduplicated_separately_from_entry() -> None:
    value = payload()
    value["action"] = "exit_filled"
    value["performance_event"].update(
        {
            "event_type": "take_profit_exit",
            "current_price": "22042",
            "realized_pnl": "420",
            "fill_hash": "e" * 64,
            "proposal_hash": "a" * 64,
        }
    )
    entry_alert = build_pending_order_alert(payload())
    exit_alert = build_paper_exit_alert(value)

    assert entry_alert is not None and exit_alert is not None
    assert entry_alert.proposal_hash != exit_alert.proposal_hash
    assert "模擬停利平倉" in exit_alert.text


def test_m15_ma20_rule_exit_reports_actual_exit_price_and_reason() -> None:
    value = payload()
    value["action"] = "exit_filled"
    value["performance_event"].update(
        {
            "event_type": "m15_ma20_rule_exit",
            "current_price": "21995",
            "realized_pnl": "-50",
            "fill_hash": "d" * 64,
            "proposal_hash": "a" * 64,
        }
    )

    alert = build_paper_exit_alert(value)

    assert alert is not None
    assert "模擬15分20MA條件失效平倉" in alert.text
    assert "平倉價：21995" in alert.text
    assert "出場原因：15分20MA條件失效平倉" in alert.text


def test_delivery_deduplication_survives_process_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "line_delivery.json"
    calls = []
    alert = build_pending_order_alert(payload())
    assert alert is not None
    first = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )
    assert first.send_once(alert) is True

    restarted = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )

    assert restarted.send_once(alert) is False
    assert len(calls) == 1
    saved = state_path.read_text(encoding="utf-8")
    assert "secret-token" not in saved and "U-recipient" not in saved
    assert '"live_order_allowed":false' in saved


def test_corrupted_delivery_state_fails_closed(tmp_path: Path) -> None:
    state_path = tmp_path / "line_delivery.json"
    state_path.write_text(
        '{"schema":"kam-line-paper-delivery-v1","sent_stages":[],"state_hash":"bad"}',
        encoding="utf-8",
    )

    try:
        LinePushNotifier("secret-token", "U-recipient", state_path=state_path)
    except ValueError as error:
        assert "delivery state" in str(error)
    else:
        raise AssertionError("corrupted delivery state must fail closed")


def performance_summary(sample_size: int) -> dict[str, object]:
    return {
        "sample_size": sample_size,
        "minimum_sample_size": 30,
        "win_rate": "60.00",
        "expectancy": "128.00",
        "profit_factor": "1.80",
        "maximum_drawdown": "440",
        "adjustment_allowed": sample_size >= 30,
        "live_order_allowed": False,
    }


def test_sample_progress_alerts_are_limited_to_10_20_and_30_closed_trades() -> None:
    observed = datetime(2026, 8, 17, 2, 0, tzinfo=UTC)

    assert build_paper_sample_milestone_alert(
        performance_summary(9), observed_at=observed
    ) is None
    alerts = [
        build_paper_sample_milestone_alert(
            performance_summary(size), observed_at=observed
        )
        for size in (10, 20, 30)
    ]
    assert all(alert is not None for alert in alerts)
    assert alerts[0] is not None and "10 / 30" in alerts[0].text
    assert alerts[1] is not None and "距離門檻還差 10 筆" in alerts[1].text
    assert alerts[2] is not None and "已達可評估門檻" in alerts[2].text


def test_sample_progress_alert_fails_closed_for_live_or_invalid_summary() -> None:
    observed = datetime(2026, 8, 17, 2, 0, tzinfo=UTC)
    live = performance_summary(10)
    live["live_order_allowed"] = True
    wrong_minimum = performance_summary(10)
    wrong_minimum["minimum_sample_size"] = 20

    assert build_paper_sample_milestone_alert(live, observed_at=observed) is None
    assert (
        build_paper_sample_milestone_alert(wrong_minimum, observed_at=observed)
        is None
    )


def test_sample_progress_alert_is_persistently_deduplicated(tmp_path: Path) -> None:
    state_path = tmp_path / "line_delivery.json"
    calls = []
    alert = build_paper_sample_milestone_alert(
        performance_summary(10),
        observed_at=datetime(2026, 8, 17, 2, 0, tzinfo=UTC),
    )
    assert alert is not None
    first = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )
    assert first.send_once(alert) is True
    restarted = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )
    assert restarted.send_once(alert) is False
    assert len(calls) == 1


def health_payload() -> dict[str, object]:
    return {
        "live_order_allowed": False,
        "open_positions": 0,
        "performance_summary": {"sample_size": 12},
    }


def test_daily_health_summary_is_persistently_deduplicated(tmp_path: Path) -> None:
    state_path = tmp_path / "line_delivery.json"
    observed = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    alert = build_paper_health_alert(
        health_payload(),
        observed_at=observed,
        quote_observed_at=observed - timedelta(seconds=3),
        journal_verified=True,
    )
    assert alert is not None
    assert "每日健康摘要" in alert.text and "12 筆" in alert.text
    calls = []
    first = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )
    assert first.send_once(alert) is True
    restarted = LinePushNotifier(
        "secret-token",
        "U-recipient",
        opener=lambda request, timeout: calls.append(request) or Response(),
        state_path=state_path,
    )
    assert restarted.send_once(alert) is False
    assert len(calls) == 1


def test_stale_quote_warns_only_during_tmf_session() -> None:
    session_time = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    alert = build_paper_health_alert(
        health_payload(),
        observed_at=session_time,
        quote_observed_at=session_time - timedelta(seconds=61),
        journal_verified=True,
    )
    assert alert is not None and "報價中斷警告" in alert.text

    weekend = datetime(2026, 8, 16, 1, 0, tzinfo=UTC)
    closed_alert = build_paper_health_alert(
        health_payload(),
        observed_at=weekend,
        quote_observed_at=weekend - timedelta(hours=1),
        journal_verified=True,
    )
    assert closed_alert is not None and "每日健康摘要" in closed_alert.text

    monday_before_open = datetime(2026, 8, 16, 17, 0, tzinfo=UTC)
    monday_alert = build_paper_health_alert(
        health_payload(),
        observed_at=monday_before_open,
        quote_observed_at=monday_before_open - timedelta(hours=1),
        journal_verified=True,
    )
    assert monday_alert is not None and "每日健康摘要" in monday_alert.text


def test_journal_integrity_warning_fails_closed_and_rejects_live_payload() -> None:
    observed = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    alert = build_paper_health_alert(
        health_payload(),
        observed_at=observed,
        quote_observed_at=observed,
        journal_verified=False,
    )
    assert alert is not None
    assert "日誌完整性警告" in alert.text and "本輪模擬處理已停止" in alert.text
    live = health_payload()
    live["live_order_allowed"] = True
    assert build_paper_health_alert(
        live,
        observed_at=observed,
        quote_observed_at=observed,
        journal_verified=False,
    ) is None


def test_refresh_fault_warns_at_three_failures_and_recovers_once(tmp_path: Path) -> None:
    state_path = tmp_path / "refresh_fault.json"
    monitor = PersistentRefreshFaultMonitor(state_path)
    first_success = datetime(2026, 8, 17, 1, 0, tzinfo=UTC)
    assert monitor.observe_success(observed_at=first_success) is None
    assert monitor.observe_failure(
        consecutive_failures=2,
        observed_at=first_success + timedelta(seconds=6),
    ) is None
    warning = monitor.observe_failure(
        consecutive_failures=3,
        observed_at=first_success + timedelta(seconds=12),
    )
    assert warning is not None
    assert "連續失敗：3 次" in warning.text
    assert first_success.isoformat() in warning.text

    restarted = PersistentRefreshFaultMonitor(state_path)
    duplicate = restarted.observe_failure(
        consecutive_failures=4,
        observed_at=first_success + timedelta(seconds=24),
    )
    assert duplicate is not None
    assert duplicate.proposal_hash == warning.proposal_hash

    recovery = restarted.observe_success(
        observed_at=first_success + timedelta(minutes=1)
    )
    assert recovery is not None and "資料連線已恢復" in recovery.text
    restarted.acknowledge_recovery()
    assert PersistentRefreshFaultMonitor(state_path).active_fault_id is None


def test_corrupted_refresh_fault_state_fails_closed(tmp_path: Path) -> None:
    state_path = tmp_path / "refresh_fault.json"
    state_path.write_text(
        '{"schema":"kam-line-refresh-fault-v1","state_hash":"bad"}',
        encoding="utf-8",
    )
    try:
        PersistentRefreshFaultMonitor(state_path)
    except ValueError as error:
        assert "refresh fault state" in str(error)
    else:
        raise AssertionError("corrupted refresh fault state must fail closed")
