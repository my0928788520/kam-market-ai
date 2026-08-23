"""Adaptive Paper-only quality gates by Taiwan session and trade direction."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
EXIT_EVENT_TYPES = {
    "stop_loss_exit",
    "profit_lock_exit",
    "take_profit_exit",
    "m15_ma20_rule_exit",
}


def _value(event: object, name: str) -> object:
    if isinstance(event, Mapping):
        return event.get(name)
    return getattr(event, name, None)


def _event_type(event: object) -> str:
    value = _value(event, "event_type")
    return str(getattr(value, "value", value))


def _observed_at(event: object) -> datetime:
    observed = _value(event, "observed_at")
    if isinstance(observed, str):
        observed = datetime.fromisoformat(observed)
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise ValueError("paper event timestamp must be timezone-aware")
    return observed


def session_name(observed_at: datetime) -> str:
    if observed_at.tzinfo is None:
        raise ValueError("quality gate timestamp must be timezone-aware")
    clock = observed_at.astimezone(TAIPEI).time().replace(tzinfo=None)
    return "regular" if time(8, 45) <= clock < time(13, 45) else "afterhours"


def _direction(entry: object) -> str:
    entry_price = Decimal(str(_value(entry, "entry_price")))
    stop_price = Decimal(str(_value(entry, "stop_loss_price")))
    return "LONG" if stop_price < entry_price else "SHORT"


def completed_outcomes_by_group(
    events: Iterable[Any],
) -> dict[str, list[Decimal]]:
    """Pair each entry with its first exit and split it into four independent groups."""
    entries: dict[str, object] = {}
    outcomes = {
        "regular_LONG": [],
        "regular_SHORT": [],
        "afterhours_LONG": [],
        "afterhours_SHORT": [],
    }
    for event in events:
        trade_id = str(_value(event, "trade_id"))
        kind = _event_type(event)
        if kind == "entry":
            entries[trade_id] = event
        elif kind in EXIT_EVENT_TYPES and trade_id in entries:
            entry = entries.pop(trade_id)
            key = f"{session_name(_observed_at(entry))}_{_direction(entry)}"
            outcomes[key].append(Decimal(str(_value(event, "realized_pnl"))))
    return outcomes


def quality_metrics(outcomes: list[Decimal]) -> dict[str, object]:
    wins = [value for value in outcomes if value > 0]
    losses = [value for value in outcomes if value < 0]
    average_win = sum(wins, Decimal(0)) / len(wins) if wins else None
    average_loss = abs(sum(losses, Decimal(0)) / len(losses)) if losses else None
    expectancy = sum(outcomes, Decimal(0)) / len(outcomes) if outcomes else None
    consecutive_losses = 0
    for value in reversed(outcomes):
        if value >= 0:
            break
        consecutive_losses += 1
    payoff_ratio = (
        average_win / average_loss
        if average_win is not None and average_loss not in {None, Decimal(0)}
        else None
    )
    return {
        "average_win": None if average_win is None else str(average_win.quantize(Decimal("0.01"))),
        "average_loss": None if average_loss is None else str(average_loss.quantize(Decimal("0.01"))),
        "payoff_ratio": None if payoff_ratio is None else str(payoff_ratio.quantize(Decimal("0.01"))),
        "expectancy": None if expectancy is None else str(expectancy.quantize(Decimal("0.01"))),
        "consecutive_losses": consecutive_losses,
    }


@dataclass(frozen=True, slots=True)
class SessionDirectionQualityGate:
    group: str
    sample_size: int
    recent_sample_size: int
    expectancy: Decimal | None
    consecutive_losses: int
    recovery_mode: bool
    action: str
    minimum_confirmation_candles: int
    dry_run: bool = True
    live_order_allowed: bool = False

    def payload(self) -> dict[str, object]:
        return {
            "group": self.group,
            "sample_size": self.sample_size,
            "recent_sample_size": self.recent_sample_size,
            "expectancy": None if self.expectancy is None else str(self.expectancy.quantize(Decimal("0.01"))),
            "consecutive_losses": self.consecutive_losses,
            "recovery_mode": self.recovery_mode,
            "action": self.action,
            "minimum_confirmation_candles": self.minimum_confirmation_candles,
            "dry_run": True,
            "live_order_allowed": False,
        }


def evaluate_session_direction_quality_gate(
    events: Iterable[Any],
    *,
    observed_at: datetime,
    direction: str,
    opportunity_mode: str,
    recovery_confirmation_candles: int = 3,
) -> SessionDirectionQualityGate:
    """Return a small-sample-safe gate; it never enables real execution."""
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("quality gate direction must be LONG or SHORT")
    key = f"{session_name(observed_at)}_{direction}"
    outcomes = completed_outcomes_by_group(events)[key]
    recent = outcomes[-5:]
    metrics = quality_metrics(recent)
    expectancy_value = metrics["expectancy"]
    expectancy = None if expectancy_value is None else Decimal(str(expectancy_value))
    consecutive_losses = int(metrics["consecutive_losses"])
    # Two losses only start a temporary repair mode; they do not permanently ban a side.
    recovery = len(outcomes) >= 2 and consecutive_losses >= 2 and expectancy is not None and expectancy < 0
    action = "ALLOW"
    confirmation = 1
    if recovery and opportunity_mode == "PAPER_EARLY_CANDIDATE":
        action = "SHADOW_ONLY"
    elif recovery:
        action = "REQUIRE_CONFIRMATION"
        confirmation = max(3, recovery_confirmation_candles)
    return SessionDirectionQualityGate(
        group=key,
        sample_size=len(outcomes),
        recent_sample_size=len(recent),
        expectancy=expectancy,
        consecutive_losses=consecutive_losses,
        recovery_mode=recovery,
        action=action,
        minimum_confirmation_candles=confirmation,
    )


__all__ = [
    "SessionDirectionQualityGate",
    "completed_outcomes_by_group",
    "evaluate_session_direction_quality_gate",
    "quality_metrics",
    "session_name",
]
