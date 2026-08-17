from kam_market_ai.notifications import watchdog_recovery_cli


class FakeNotifier:
    alert = None

    def __init__(self, token: str, recipient: str) -> None:
        assert token == "token" and recipient == "recipient"

    def send_once(self, alert) -> bool:
        type(self).alert = alert
        return True


def test_watchdog_recovery_is_utf8_safe_and_expands_values(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "KAM_LINE_CHANNEL_ACCESS_TOKEN=token\n"
        "KAM_LINE_RECIPIENT_USER_ID=recipient\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(watchdog_recovery_cli, "LinePushNotifier", FakeNotifier)

    result = watchdog_recovery_cli.send_watchdog_recovery(
        env,
        symbol="TMFQ6",
        session="afterhours",
        health_url="http://127.0.0.1:8765/api/five-timeframe/health",
    )

    assert result == {"success": True, "live_order_allowed": False}
    text = FakeNotifier.alert.text
    assert "商品：TMFQ6" in text
    assert "時段：夜盤" in text
    assert "$Symbol" not in text
    assert "DateTimeOffset" not in text
    assert "�" not in text
    assert FakeNotifier.alert.live_order_allowed is False
