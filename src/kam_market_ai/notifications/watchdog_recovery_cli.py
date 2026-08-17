"""UTF-8-safe watchdog recovery notification for the paper-only dashboard."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from kam_market_ai.config import load_dotenv_values

from .line_pending_order import LinePendingOrderAlert, LinePushNotifier


def send_watchdog_recovery(
    env_path: str | Path,
    *,
    symbol: str,
    session: str,
    health_url: str,
) -> dict[str, object]:
    values = load_dotenv_values(env_path)
    try:
        notifier = LinePushNotifier(
            values.get("KAM_LINE_CHANNEL_ACCESS_TOKEN", ""),
            values.get("KAM_LINE_RECIPIENT_USER_ID", ""),
        )
        now = datetime.now(UTC)
        session_label = "夜盤" if session == "afterhours" else "日盤"
        identity = f"watchdog-recovery:{symbol}:{session}:{now.isoformat()}"
        alert = LinePendingOrderAlert(
            sha256(identity.encode("utf-8")).hexdigest(),
            "\n".join(
                (
                    "KAM Paper Trading 看門狗已恢復服務",
                    f"商品：{symbol or '自動選擇近月合約'}",
                    f"時段：{session_label}",
                    f"健康網址：{health_url}",
                    f"恢復時間：{now.astimezone().isoformat()}",
                    "安全：僅啟動 Paper Trading，不會送出真實委託",
                )
            ),
            now + timedelta(minutes=5),
        )
        sent = notifier.send_once(alert)
    except (OSError, RuntimeError, TimeoutError, ValueError):
        return {"success": False, "live_order_allowed": False}
    return {"success": sent, "live_order_allowed": False}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--symbol", default="")
    parser.add_argument("--session", choices=("regular", "afterhours"), required=True)
    parser.add_argument("--health-url", required=True)
    args = parser.parse_args(argv)
    result = send_watchdog_recovery(
        args.env,
        symbol=args.symbol,
        session=args.session,
        health_url=args.health_url,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
