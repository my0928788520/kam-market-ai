from pathlib import Path

from kam_market_ai.notifications.line_alert_test_cli import main, send_line_configuration_test


class FakeNotifier:
    token = ""
    recipient = ""

    def __init__(self, token: str, recipient: str) -> None:
        if not token or not recipient:
            raise ValueError("incomplete")
        type(self).token = token
        type(self).recipient = recipient

    def send_once(self, alert) -> bool:
        assert "Paper Trading" in alert.text
        assert "不會建立或送出真實委託" in alert.text
        assert alert.live_order_allowed is False
        return True


def write_env(path: Path) -> None:
    path.write_text(
        "KAM_LINE_CHANNEL_ACCESS_TOKEN=secret-token\n"
        "KAM_LINE_RECIPIENT_USER_ID=U-recipient\n",
        encoding="utf-8",
    )


def test_configuration_test_sends_only_sanitized_paper_message(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    write_env(env_path)
    result = send_line_configuration_test(env_path, notifier_factory=FakeNotifier)
    assert result == {
        "success": True,
        "status": "LINE_TEST_COMPLETED",
        "paper_only": True,
        "live_order_allowed": False,
    }
    assert FakeNotifier.token == "secret-token"
    assert FakeNotifier.recipient == "U-recipient"
    assert "secret-token" not in repr(result)
    assert "U-recipient" not in repr(result)


def test_configuration_test_fails_closed_when_env_is_incomplete(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("KAM_LINE_CHANNEL_ACCESS_TOKEN=\n", encoding="utf-8")
    result = send_line_configuration_test(env_path, notifier_factory=FakeNotifier)
    assert result["success"] is False
    assert result["failure_stage"] == "LINE_ALERT_CONFIGURATION_ERROR"
    assert result["live_order_allowed"] is False


def test_cli_requires_explicit_send_test_flag(capsys) -> None:
    assert main([]) == 2
    output = capsys.readouterr().out
    assert "EXPLICIT_TEST_CONFIRMATION_REQUIRED" in output
    assert '"live_order_allowed": false' in output
