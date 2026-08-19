"""Persistent observation-only tracker for C-grade Paper opportunities."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from json import dumps, loads
from os import replace
from pathlib import Path
from typing import Any

SCHEMA = "kam-paper-opportunity-observations-v1"
THRESHOLDS = (Decimal(30), Decimal(60), Decimal(120))


class PaperOpportunityTracker:
    """Measure missed moves without creating an order or touching the broker."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = None if path is None else Path(path)
        self.active: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self._load()

    def observe(
        self,
        *,
        grade: str | None,
        direction: str | None,
        price: Decimal,
        observed_at: datetime,
    ) -> None:
        if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(observed_at):
            raise ValueError("observed_at must be UTC timezone-aware")
        if not price.is_finite() or price <= 0:
            raise ValueError("price must be positive and finite")
        is_shadow = grade == "C" and direction in {"LONG", "SHORT"}
        if self.active is not None:
            if not is_shadow or self.active["direction"] != direction:
                self._finish(observed_at)
            else:
                self._mark(price, observed_at)
                self._save()
                return
        if is_shadow:
            stamp = observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
            self.active = {
                "signal_id": sha256(f"{direction}|{price}|{stamp}".encode()).hexdigest(),
                "direction": direction,
                "entry_price": str(price),
                "started_at": stamp,
                "last_observed_at": stamp,
                "max_favorable_points": "0",
                "max_adverse_points": "0",
                "dry_run": True,
                "live_order_allowed": False,
            }
            self._save()

    def safe_payload(self) -> dict[str, object]:
        combined = [*self.records, *([self.active] if self.active else [])]
        reached = {
            str(int(level)): sum(
                Decimal(str(item["max_favorable_points"])) >= level
                for item in combined
            )
            for level in THRESHOLDS
        }
        avoided = sum(
            Decimal(str(item["max_favorable_points"])) < Decimal(30)
            and Decimal(str(item["max_adverse_points"])) >= Decimal(30)
            for item in self.records
        )
        return {
            "sample_size": len(combined),
            "completed_samples": len(self.records),
            "active": self.active is not None,
            "reached_30_points": reached["30"],
            "reached_60_points": reached["60"],
            "reached_120_points": reached["120"],
            "avoided_false_signals": avoided,
            "dry_run": True,
            "live_order_allowed": False,
        }

    def _mark(self, price: Decimal, observed_at: datetime) -> None:
        if self.active is None:
            return
        entry = Decimal(str(self.active["entry_price"]))
        move = price - entry
        favorable = move if self.active["direction"] == "LONG" else -move
        adverse = -move if self.active["direction"] == "LONG" else move
        self.active["max_favorable_points"] = str(max(
            Decimal(str(self.active["max_favorable_points"])), favorable, Decimal(0)
        ))
        self.active["max_adverse_points"] = str(max(
            Decimal(str(self.active["max_adverse_points"])), adverse, Decimal(0)
        ))
        self.active["last_observed_at"] = observed_at.isoformat().replace("+00:00", "Z")

    def _finish(self, observed_at: datetime) -> None:
        if self.active is None:
            return
        self.active["ended_at"] = observed_at.isoformat().replace("+00:00", "Z")
        self.records.append(self.active)
        self.records = self.records[-200:]
        self.active = None
        self._save()

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": SCHEMA, "active": self.active, "records": self.records}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        replace(temporary, self.path)

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            payload = loads(self.path.read_text(encoding="utf-8"))
            if payload.get("schema") != SCHEMA:
                return
            self.active = payload.get("active") if isinstance(payload.get("active"), dict) else None
            records = payload.get("records")
            self.records = records[-200:] if isinstance(records, list) else []
        except (OSError, ValueError, TypeError):
            self.active = None
            self.records = []


__all__ = ["PaperOpportunityTracker"]
