"""Named deterministic fixture scenarios for Replay dashboard consumers."""
REPLAY_DASHBOARD_FIXTURE_VERSION="1.0"
REPLAY_DASHBOARD_FIXTURE_NAMES=frozenset({"initial_frame","no_change","direction_changed","confidence_increased","confidence_decreased","risk_increased","risk_decreased","next_step_changed","mixed_timeframe_changed","higher_timeframe_changed","single_module_changed","stale_current_frame","blocked_current_frame","unavailable_decision","data_gap","source_correction","evaluation_failure","scenario_mismatch","run_mismatch","deterministic_comparison"})
