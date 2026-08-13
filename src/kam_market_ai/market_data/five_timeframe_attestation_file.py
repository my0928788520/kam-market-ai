"""JSON file boundary for explicit five-timeframe completeness attestations.

The template intentionally leaves calendar classifications blank.  Operators
or a future verified exchange-calendar adapter must supply them; this module
never guesses a trading date, week identity, holiday, or completeness state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping

from .fubon_live_five_timeframe_verifier import CandleClassification

ATTESTATION_FILE_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class LoadedFiveTimeframeAttestation:
    classifications: tuple[CandleClassification, ...]
    complete_trading_dates: tuple[date, ...]
    complete_week_starts: tuple[date, ...]


def build_attestation_template(payload: Mapping[str, object]) -> dict[str, object]:
    """Build an editable, fail-closed template from one verifier response."""
    if payload.get("status") != "ATTESTATION_REQUIRED":
        raise ValueError("ATTESTATION_TEMPLATE_REQUIRES_PARTIAL_VERIFIER_PAYLOAD")
    starts = payload.get("source_candle_starts")
    if not isinstance(starts, list) or not starts or not all(isinstance(item, str) for item in starts):
        raise ValueError("ATTESTATION_TEMPLATE_SOURCE_STARTS_REQUIRED")
    return {
        "version": ATTESTATION_FILE_VERSION,
        "symbol": payload.get("symbol"),
        "session": payload.get("session"),
        "source_timeframe": payload.get("source_timeframe"),
        "classifications": [
            {"candle_start": item, "trading_date": None, "week_start": None}
            for item in starts
        ],
        "complete_trading_dates": [],
        "complete_week_starts": [],
        "verified_by_operator": False,
        "instructions": (
            "Fill every classification and completeness list from a verified "
            "exchange calendar, then set verified_by_operator to true."
        ),
    }


def write_attestation_template(path: str | Path, payload: Mapping[str, object]) -> Path:
    target = Path(path)
    target.write_text(
        json.dumps(build_attestation_template(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def load_verified_attestation(path: str | Path) -> LoadedFiveTimeframeAttestation:
    """Load only a complete, explicitly operator-verified attestation file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != ATTESTATION_FILE_VERSION:
        raise ValueError("ATTESTATION_FILE_VERSION_INVALID")
    if raw.get("verified_by_operator") is not True:
        raise ValueError("ATTESTATION_FILE_OPERATOR_VERIFICATION_REQUIRED")
    rows = raw.get("classifications")
    dates = raw.get("complete_trading_dates")
    weeks = raw.get("complete_week_starts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("ATTESTATION_FILE_CLASSIFICATIONS_REQUIRED")
    if not isinstance(dates, list) or not dates or not all(isinstance(item, str) for item in dates):
        raise ValueError("ATTESTATION_FILE_COMPLETE_DATES_REQUIRED")
    if not isinstance(weeks, list) or not weeks or not all(isinstance(item, str) for item in weeks):
        raise ValueError("ATTESTATION_FILE_COMPLETE_WEEKS_REQUIRED")
    classifications: list[CandleClassification] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("ATTESTATION_FILE_CLASSIFICATION_INVALID")
        start = row.get("candle_start")
        trading_date = row.get("trading_date")
        week_start = row.get("week_start")
        if not all(isinstance(item, str) and item for item in (start, trading_date, week_start)):
            raise ValueError("ATTESTATION_FILE_CLASSIFICATION_INCOMPLETE")
        classifications.append(
            CandleClassification(
                datetime.fromisoformat(start),
                date.fromisoformat(trading_date),
                date.fromisoformat(week_start),
            )
        )
    return LoadedFiveTimeframeAttestation(
        tuple(classifications),
        tuple(date.fromisoformat(item) for item in dates),
        tuple(date.fromisoformat(item) for item in weeks),
    )


__all__ = [
    "ATTESTATION_FILE_VERSION",
    "LoadedFiveTimeframeAttestation",
    "build_attestation_template",
    "load_verified_attestation",
    "write_attestation_template",
]
