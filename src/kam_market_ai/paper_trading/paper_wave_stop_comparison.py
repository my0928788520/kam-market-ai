"""Persistent, observation-only comparison of fixed and equal-wave stops."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from json import dumps, loads
from os import replace
from pathlib import Path
from typing import Any

SCHEMA = "kam-paper-wave-stop-comparison-v1"


class PaperWaveStopComparisonTracker:
    """Compare two paper stops without changing orders, fills, or positions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = None if path is None else Path(path)
        self.active: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self._load()

    def start(
        self,
        *,
        trade_id: str,
        side: str,
        entry_price: Decimal,
        fixed_stop_price: Decimal,
        observed_at: datetime,
    ) -> None:
        self._validate_time(observed_at)
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.active is not None and self.active.get("trade_id") == trade_id:
            return
        if self.active is not None:
            self.finish(observed_at=observed_at, actual_exit_price=None)
        stamp = self._stamp(observed_at)
        self.active = {
            "trade_id": trade_id,
            "side": side,
            "entry_price": str(entry_price),
            "fixed_stop_price": str(fixed_stop_price),
            "wave_stop_price": None,
            "fixed_stop_at": None,
            "wave_stop_at": None,
            "fixed_stop_exit_price": None,
            "wave_stop_exit_price": None,
            "fixed_stop_survived_by_wave": False,
            "max_favorable_points": "0",
            "max_adverse_points": "0",
            "started_at": stamp,
            "last_observed_at": stamp,
            "dry_run": True,
            "live_order_allowed": False,
        }
        self._save()

    def observe(
        self,
        *,
        trade_id: str,
        price: Decimal,
        observed_at: datetime,
        wave_pivot_price: Decimal | None,
        buffer_points: Decimal,
    ) -> None:
        self._validate_time(observed_at)
        if self.active is None or self.active.get("trade_id") != trade_id:
            return
        side = str(self.active["side"])
        entry = Decimal(str(self.active["entry_price"]))
        move = price - entry
        favorable = move if side == "BUY" else -move
        adverse = -move if side == "BUY" else move
        self.active["max_favorable_points"] = str(max(
            Decimal(str(self.active["max_favorable_points"])), favorable, Decimal(0)
        ))
        self.active["max_adverse_points"] = str(max(
            Decimal(str(self.active["max_adverse_points"])), adverse, Decimal(0)
        ))

        if wave_pivot_price is not None:
            candidate = (
                wave_pivot_price - buffer_points
                if side == "BUY"
                else wave_pivot_price + buffer_points
            )
            existing = self.active.get("wave_stop_price")
            if existing is None:
                self.active["wave_stop_price"] = str(candidate)
            else:
                previous = Decimal(str(existing))
                self.active["wave_stop_price"] = str(
                    max(previous, candidate) if side == "BUY" else min(previous, candidate)
                )

        fixed_stop = Decimal(str(self.active["fixed_stop_price"]))
        fixed_hit = price <= fixed_stop if side == "BUY" else price >= fixed_stop
        if fixed_hit and self.active["fixed_stop_at"] is None:
            self.active["fixed_stop_at"] = self._stamp(observed_at)
            self.active["fixed_stop_exit_price"] = str(price)
            wave_value = self.active.get("wave_stop_price")
            wave_hit_now = wave_value is not None and (
                price <= Decimal(str(wave_value))
                if side == "BUY"
                else price >= Decimal(str(wave_value))
            )
            self.active["fixed_stop_survived_by_wave"] = not wave_hit_now

        wave_value = self.active.get("wave_stop_price")
        wave_hit = wave_value is not None and (
            price <= Decimal(str(wave_value))
            if side == "BUY"
            else price >= Decimal(str(wave_value))
        )
        if wave_hit and self.active["wave_stop_at"] is None:
            self.active["wave_stop_at"] = self._stamp(observed_at)
            self.active["wave_stop_exit_price"] = str(price)
        self.active["last_observed_at"] = self._stamp(observed_at)
        self._save()

    def finish(
        self,
        *,
        observed_at: datetime,
        actual_exit_price: Decimal | None,
    ) -> None:
        self._validate_time(observed_at)
        if self.active is None:
            return
        self.active["ended_at"] = self._stamp(observed_at)
        self.active["actual_exit_price"] = (
            None if actual_exit_price is None else str(actual_exit_price)
        )
        self.records.append(self.active)
        self.records = self.records[-200:]
        self.active = None
        self._save()

    def safe_payload(self) -> dict[str, object]:
        combined = [*self.records, *([self.active] if self.active else [])]
        fixed_stops = sum(item.get("fixed_stop_at") is not None for item in combined)
        wave_stops = sum(item.get("wave_stop_at") is not None for item in combined)
        saved = sum(item.get("fixed_stop_survived_by_wave") is True for item in combined)
        completed = len(self.records)
        if completed < 10:
            verdict = "樣本不足"
        elif saved > 0 and wave_stops < fixed_stops:
            verdict = "波浪停損較佳"
        elif fixed_stops < wave_stops:
            verdict = "固定停損較佳"
        else:
            verdict = "兩者接近"
        return {
            "sample_size": len(combined),
            "completed_samples": completed,
            "active": self.active is not None,
            "fixed_stop_exits": fixed_stops,
            "wave_stop_exits": wave_stops,
            "saved_by_wave_stop": saved,
            "verdict": verdict,
            "dry_run": True,
            "live_order_allowed": False,
        }

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "active": self.active, "records": self.records}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        replace(temporary, self.path)

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            payload = loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema") != SCHEMA:
                return
            active = payload.get("active")
            records = payload.get("records")
            self.active = active if isinstance(active, dict) else None
            self.records = records[-200:] if isinstance(records, list) else []
        except (OSError, ValueError, TypeError):
            self.active = None
            self.records = []

    @staticmethod
    def _validate_time(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("observed_at must be UTC timezone-aware")

    @staticmethod
    def _stamp(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["PaperWaveStopComparisonTracker"]
