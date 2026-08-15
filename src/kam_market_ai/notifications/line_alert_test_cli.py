"""Explicit, paper-only LINE configuration test with sanitized output."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from kam_market_ai.config import load_dotenv_values
from kam_market_ai.notifications.line_pending_order import LinePendingOrderAlert, LinePushNotifier


def send_line_configuration_test(
    env_path: str | Path,
    *,
    notifier_factory: Callable[[str, str], LinePushNotifier] = LinePushNotifier,
) -> dict[str, object]:
    """Send one harmless text message without creating a proposal or order."""
    values = load_dotenv_values(env_path)
    try:
        notifier = notifier_factory(
            values.get("KAM_LINE_CHANNEL_ACCESS_TOKEN", ""),
            values.get("KAM_LINE_RECIPIENT_USER_ID", ""),
        )
    except ValueError:
        return {
            "success": False,
            "failure_stage": "LINE_ALERT_CONFIGURATION_ERROR",
            "paper_only": True,
            "live_order_allowed": False,
        }

    alert = LinePendingOrderAlert(
        proposal_hash="0" * 64,
        text="\n".join(
            (
                "KAM LINE 通知測試成功",
                "目前狀態：Paper Trading",
                "安全：不會建立或送出真實委託",
            )
        ),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    try:
        sent = notifier.send_once(alert)
    except (OSError, RuntimeError, TimeoutError):
        return {
            "success": False,
            "failure_stage": "LINE_PUSH_FAILED",
            "paper_only": True,
            "live_order_allowed": False,
        }
    return {
        "success": sent,
        "status": "LINE_TEST_COMPLETED" if sent else "LINE_TEST_NOT_SENT",
        "paper_only": True,
        "live_order_allowed": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send one paper-only KAM LINE test notification.")
    parser.add_argument("--env", default=".env")
    parser.add_argument("--send-test", action="store_true")
    args = parser.parse_args(argv)
    if not args.send_test:
        print(
            json.dumps(
                {
                    "success": False,
                    "failure_stage": "EXPLICIT_TEST_CONFIRMATION_REQUIRED",
                    "paper_only": True,
                    "live_order_allowed": False,
                }
            )
        )
        return 2
    result = send_line_configuration_test(args.env)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
