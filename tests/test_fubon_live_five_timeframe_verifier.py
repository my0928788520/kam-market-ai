import json
from datetime import date, datetime
from pathlib import Path

import pytest

from kam_market_ai.market_data.fubon_five_timeframe_pipeline import FubonFiveTimeframeCandlePipeline
from kam_market_ai.market_data.fubon_live_five_timeframe_verifier import (
    CandleClassification,
    FubonLiveFiveTimeframeVerifier,
)
from kam_market_ai.market_data.fubon_live_five_timeframe_verifier_cli import main
from kam_market_ai.market_data.fubon_neo import (
    AuthorizedMarketDataClients,
    FubonIntradayCandlesAdapter,
    ResolvedFuturesContract,
    VerifiedContractResolver,
)
from kam_market_ai.models import Instrument


class WebSocket:
    def on(self, *_args): pass
    def off(self, *_args): pass
    def connect(self): pass
    def subscribe(self, *_args): pass
    def unsubscribe(self, *_args): pass
    def disconnect(self): pass


class Intraday:
    def __init__(self) -> None:
        self.calls = []

    def candles(self, **params):
        self.calls.append(params)
        return {"symbol": params["symbol"], "timeframe": params["timeframe"], "data": [
            {"date": "2026-08-03T09:00:00+08:00", "open": 100, "high": 103, "low": 99, "close": 102, "volume": 10},
            {"date": "2026-08-03T10:00:00+08:00", "open": 102, "high": 105, "low": 101, "close": 104, "volume": 12},
        ]}


class Rest:
    def __init__(self, intraday):
        self.intraday = intraday
        self.historical = object()


def verifier(*, after_hours: bool = False):
    intraday = Intraday()
    clients = AuthorizedMarketDataClients(WebSocket(), Rest(intraday), WebSocket(), Rest(Intraday()))
    resolver = VerifiedContractResolver((
        ResolvedFuturesContract(Instrument.TMF, "TMFH6", after_hours),
    ))
    pipeline = FubonFiveTimeframeCandlePipeline(FubonIntradayCandlesAdapter(clients, resolver))
    return FubonLiveFiveTimeframeVerifier(pipeline), intraday


def test_probe_stops_at_attestation_required_and_exposes_safe_source_identity() -> None:
    target, intraday = verifier()
    payload = target.run(symbol="TMFH6", session="NORMAL")

    assert payload["success"] is False
    assert payload["status"] == "ATTESTATION_REQUIRED"
    assert payload["decision_preview"]["decision_status"] == "BLOCKED"
    assert payload["decision_preview"]["action"] == "HOLD"
    assert payload["decision_preview"]["blockers"] == [
        "FIVE_TIMEFRAME_DATA_INCOMPLETE"
    ]
    assert payload["analysis_preview"]["analysis_status"] == "provisional_current_periods"
    assert payload["analysis_preview"]["three_second_summary"]["headline"] == "日週線形成中"
    assert "CURRENT_DAY_WEEK_BARS_ARE_PROVISIONAL" in payload["analysis_preview"]["blockers"]
    assert payload["analysis_preview"]["decision_status"] == "BLOCKED"
    assert payload["external_endpoint_call_count"] == 3
    assert payload["symbol"] == "TMFH6"
    assert len(payload["source_candle_starts"]) == 2
    assert [call["timeframe"] for call in intraday.calls] == ["5", "15", "60"]
    assert payload["account_connected"] is False
    assert payload["trading_enabled"] is False
    assert "candles" not in payload and "series" not in payload


def test_exact_operator_attestation_reaches_ready_five_timeframes() -> None:
    target, _ = verifier()
    first = "2026-08-03T01:00:00+00:00"
    second = "2026-08-03T02:00:00+00:00"
    classified = (
        CandleClassification(datetime.fromisoformat(first), date(2026, 8, 3), date(2026, 8, 3)),
        CandleClassification(datetime.fromisoformat(second), date(2026, 8, 3), date(2026, 8, 3)),
    )

    payload = target.run(
        symbol="TMFH6",
        session="NORMAL",
        classifications=classified,
        complete_trading_dates=(date(2026, 8, 3),),
        complete_week_starts=(date(2026, 8, 3),),
    )

    assert payload["success"] is True
    assert payload["status"] == "READY_VERIFIED_FIVE_TIMEFRAMES"
    assert payload["decision_preview"]["decision_status"] == "BLOCKED"
    assert payload["decision_preview"]["action"] == "HOLD"
    assert payload["decision_preview"]["blockers"] == [
        "TIMEFRAME_STATE_CLASSIFICATION_REQUIRED"
    ]
    assert payload["analysis_preview"]["decision_status"] == "BLOCKED"
    assert payload["analysis_preview"]["action"] == "HOLD"
    assert payload["analysis_preview"]["timeframes"]["5m"]["status"] != "unsupported"
    assert "M5_ANALYSIS_ENGINE_REQUIRED" not in payload["analysis_preview"]["blockers"]
    assert "TRADING_DECISION_MAPPING_NOT_APPROVED" in payload["analysis_preview"]["blockers"]
    assert payload["analysis_preview"]["decision_diagnostics"]["observation_only"] is True
    assert payload["analysis_preview"]["three_second_summary"]["action"] == "HOLD"
    assert payload["analysis_preview"]["three_second_summary"]["decision_status"] == "BLOCKED"
    assert payload["analysis_preview"]["raw_candles_retained"] is False
    assert payload["loaded_timeframes"] == ["5m", "15m", "60m", "1d", "1w"]
    assert payload["verified_trading_dates"] == ["2026-08-03"]


def test_missing_or_extra_classification_fails_closed() -> None:
    target, _ = verifier()
    one = CandleClassification(
        datetime.fromisoformat("2026-08-03T01:00:00+00:00"),
        date(2026, 8, 3),
        date(2026, 8, 3),
    )
    with pytest.raises(ValueError, match="CLASSIFICATION_COVERAGE_MISMATCH"):
        target.run(
            symbol="TMFH6",
            session="NORMAL",
            classifications=(one,),
            complete_trading_dates=(date(2026, 8, 3),),
            complete_week_starts=(date(2026, 8, 3),),
        )


def test_current_trading_day_cannot_be_attested_complete() -> None:
    target, _ = verifier()
    classified = tuple(
        CandleClassification(
            datetime.fromisoformat(item),
            date(2026, 8, 13),
            date(2026, 8, 10),
        )
        for item in (
            "2026-08-03T01:00:00+00:00",
            "2026-08-03T02:00:00+00:00",
        )
    )

    with pytest.raises(ValueError, match="CURRENT_TRADING_DATE_CANNOT_BE_COMPLETE"):
        target.run(
            symbol="TMFH6",
            session=None,
            classifications=classified,
            complete_trading_dates=(date(2026, 8, 13),),
            complete_week_starts=(date(2026, 8, 10),),
            verified_at=datetime.fromisoformat("2026-08-13T04:30:00+00:00"),
        )


def test_cli_requires_explicit_live_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--symbol", "TMFH6", "--session", "NORMAL"]) == 2
    assert json.loads(capsys.readouterr().out)["failure_stage"] == "LIVE_FLAG_REQUIRED"


def test_live_verifier_contains_no_account_or_order_capability() -> None:
    import kam_market_ai.market_data.fubon_live_five_timeframe_verifier as module

    source = Path(module.__file__).read_text(encoding="utf-8").lower()
    assert "place_order" not in source
    assert "subscribe(" not in source

def test_regular_session_omits_provider_session_from_all_requests() -> None:
    target, intraday = verifier()

    payload = target.run(symbol="TMFH6", session=None)

    assert payload["session"] is None
    assert intraday.calls == [
        {"symbol": "TMFH6", "timeframe": "5"},
        {"symbol": "TMFH6", "timeframe": "15"},
        {"symbol": "TMFH6", "timeframe": "60"},
    ]


def test_after_hours_session_passes_official_token_to_all_requests() -> None:
    target, intraday = verifier(after_hours=True)

    payload = target.run(
        symbol="TMFH6",
        session="afterhours",
        after_hours=True,
    )

    assert payload["session"] == "afterhours"
    assert intraday.calls == [
        {"symbol": "TMFH6", "timeframe": "5", "session": "afterhours"},
        {"symbol": "TMFH6", "timeframe": "15", "session": "afterhours"},
        {"symbol": "TMFH6", "timeframe": "60", "session": "afterhours"},
    ]
