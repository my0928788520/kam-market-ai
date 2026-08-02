"""Explicit local entry point for a bounded read-only WebSocket observation."""
from __future__ import annotations

import argparse
import json

from ..authorization.bootstrap import AuthorizationBootstrap, AuthorizationFailure, AuthorizationSettings
from ..config import Settings, TRADING_ENABLED
from .realtime_probe import ActiveContractProbe, BoundedReactionObserver


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("--after-hours", action="store_true")
    args = parser.parse_args()
    try:
        bootstrap = AuthorizationBootstrap().run(AuthorizationSettings.from_local_env(), dry_run=False)
    except AuthorizationFailure as error:
        print(json.dumps({"failure_stage": error.stage.value}))
        return 1
    try:
        contracts = ActiveContractProbe(bootstrap.clients).resolve(after_hours=args.after_hours)
    except Exception as error:
        print(json.dumps({"failure_stage": "CONTRACT_DISCOVERY_ERROR", "error_type": type(error).__name__}))
        return 1
    try:
        report = BoundedReactionObserver(bootstrap.clients, Settings.load().database_path).observe(
            contracts, duration_seconds=args.duration_seconds, after_hours=args.after_hours
        )
    except Exception as error:
        print(json.dumps({"failure_stage": "OBSERVER_ERROR", "error_type": type(error).__name__}))
        return 1
    print(json.dumps({
        "active_tx_symbol": report.active_tx_symbol, "active_tmf_symbol": report.active_tmf_symbol,
        "ir0001_events_received": report.event_count_by_instrument.get("TAIEX", 0),
        "tx_events_received": report.event_count_by_instrument.get("TX", 0),
        "tmf_events_received": report.event_count_by_instrument.get("MTX", 0),
        "exchange_timestamp_missing_count": report.exchange_timestamp_missing_count,
        "mapper_failure_count": report.mapper_failure_count, "event_cluster_count": report.event_cluster_count,
        "reaction_analysis_count": report.reaction_analysis_count,
        "reaction_chain_storage_count": report.reaction_storage_count,
        "first_event_count_by_instrument": report.first_event_count_by_instrument,
        "event_order_count": report.event_order_count, "reaction_class_count": report.reaction_class_count,
        "alignment_type_count": report.alignment_type_count,
        "unsubscribe_success": report.unsubscribe_success, "disconnect_success": report.disconnect_success,
        "receive_order_differs_from_exchange_order": report.receive_order_differs_from_exchange_order,
        "callback_or_timestamp_issue": report.callback_or_timestamp_issue,
        "reconnect_issue": report.reconnect_issue, "trading_enabled": TRADING_ENABLED,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
