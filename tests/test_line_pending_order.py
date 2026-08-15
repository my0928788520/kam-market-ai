from datetime import UTC, datetime, timedelta
from json import loads

from kam_market_ai.notifications.line_pending_order import (
    LinePushNotifier,
    build_paper_exit_alert,
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
    assert "偏多" in alert.text and "TMFH6" in alert.text
    assert "停損：21980" in alert.text and "停利：22040" in alert.text
    for forbidden in ("account", "password", "token", "certificate"):
        assert forbidden not in alert.text.lower()


def test_non_entry_or_live_capable_payload_never_builds_an_alert() -> None:
    value = payload()
    value["action"] = "hold"
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
