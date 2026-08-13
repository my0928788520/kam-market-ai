import json
from datetime import date

import pytest

from kam_market_ai.market_data.five_timeframe_attestation_file import (
    build_attestation_template,
    load_verified_attestation,
    write_attestation_template,
)


def partial_payload() -> dict[str, object]:
    return {
        "status": "ATTESTATION_REQUIRED",
        "symbol": "TMFH6",
        "session": None,
        "source_timeframe": "60m",
        "source_candle_starts": [
            "2026-08-13T00:45:00+00:00",
            "2026-08-13T01:45:00+00:00",
        ],
    }


def test_template_preserves_source_identity_without_guessing_calendar_labels() -> None:
    value = build_attestation_template(partial_payload())

    assert value["symbol"] == "TMFH6"
    assert value["verified_by_operator"] is False
    assert value["complete_trading_dates"] == []
    assert value["classifications"] == [
        {
            "candle_start": "2026-08-13T00:45:00+00:00",
            "trading_date": None,
            "week_start": None,
        },
        {
            "candle_start": "2026-08-13T01:45:00+00:00",
            "trading_date": None,
            "week_start": None,
        },
    ]


def test_template_round_trip_loads_only_after_explicit_verification(tmp_path) -> None:
    path = write_attestation_template(tmp_path / "attestation.json", partial_payload())
    raw = json.loads(path.read_text(encoding="utf-8"))
    for row in raw["classifications"]:
        row["trading_date"] = "2026-08-13"
        row["week_start"] = "2026-08-10"
    raw["complete_trading_dates"] = ["2026-08-13"]
    raw["complete_week_starts"] = ["2026-08-10"]
    raw["verified_by_operator"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = load_verified_attestation(path)

    assert len(loaded.classifications) == 2
    assert loaded.complete_trading_dates == (date(2026, 8, 13),)
    assert loaded.complete_week_starts == (date(2026, 8, 10),)


def test_unverified_or_incomplete_file_fails_closed(tmp_path) -> None:
    path = write_attestation_template(tmp_path / "attestation.json", partial_payload())

    with pytest.raises(ValueError, match="OPERATOR_VERIFICATION_REQUIRED"):
        load_verified_attestation(path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["verified_by_operator"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="COMPLETE_DATES_REQUIRED"):
        load_verified_attestation(path)
