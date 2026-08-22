import json
from datetime import UTC, datetime
from io import BytesIO

from kam_market_ai.notifications.session_close_report import (
    ExternalMarketContext,
    PublicDelayedReferenceSource,
    ReferenceReading,
    build_session_close_alert,
    desired_live_session,
    due_session_close,
)


def payload() -> dict[str, object]:
    return {
        "market_data_only": True,
        "live_order_allowed": False,
        "analysis_preview": {
            "timeframes": {
                "1d": {"price_vs_ma60": "above"},
                "60m": {"market_bias": "bullish"},
                "15m": {
                    "price_vs_ma20": "above",
                    "ma20_direction": "rising",
                    "volume_ratio_20": 1.2,
                    "volatility_ratio_20": 1.4,
                },
            }
        },
    }


def context() -> ExternalMarketContext:
    return ExternalMarketContext(
        (
            ReferenceReading("標普期貨", "ES=F", 6500, 0.5, None, "delayed"),
            ReferenceReading("那指期貨", "NQ=F", 25000, 0.7, None, "delayed"),
            ReferenceReading("道指期貨", "YM=F", 47000, 0.3, None, "delayed"),
            ReferenceReading("美元台幣", "TWD=X", 31.8, -0.1, None, "delayed"),
        )
    )


def test_close_windows_use_taipei_day_and_night_sessions() -> None:
    assert due_session_close(datetime(2026, 8, 21, 5, 50, tzinfo=UTC)) == "regular"
    assert due_session_close(datetime(2026, 8, 21, 21, 5, tzinfo=UTC)) == "afterhours"
    assert due_session_close(datetime(2026, 8, 21, 12, 0, tzinfo=UTC)) is None


def test_continuous_service_switches_sessions_on_taipei_schedule() -> None:
    assert desired_live_session(datetime(2026, 8, 21, 0, 45, tzinfo=UTC)) == "regular"
    assert desired_live_session(datetime(2026, 8, 21, 6, 59, tzinfo=UTC)) == "regular"
    assert desired_live_session(datetime(2026, 8, 21, 7, 0, tzinfo=UTC)) == "afterhours"
    assert desired_live_session(datetime(2026, 8, 21, 21, 5, tzinfo=UTC)) == "afterhours"


def test_night_report_combines_direction_volume_volatility_us_futures_and_fx() -> None:
    alert = build_session_close_alert(
        payload(),
        context(),
        session="afterhours",
        observed_at=datetime(2026, 8, 21, 21, 5, tzinfo=UTC),
    )

    assert "KAM 夜盤收盤分析" in alert.text
    assert "多方 95%｜空方 5%" in alert.text
    assert "成交量：1.20倍20期均量" in alert.text
    assert "獨立波動：1.40倍20期均幅" in alert.text
    assert "標普期貨：+0.50%（延遲參考）" in alert.text
    assert "當盤占比為線型量價規則估計；歷史校準率另列" in alert.text
    assert alert.live_order_allowed is False


def test_report_includes_line_volume_confirmation_and_historical_calibration() -> None:
    calibration = {
        "current_confirmation": {
            "line_confirmation": "confirmed",
            "volume_confirmation": "放量確認",
            "historical_group": {
                "calibrated_success_rate": 62.5,
                "sample_size": 40,
            },
        }
    }
    alert = build_session_close_alert(
        payload(),
        context(),
        session="regular",
        observed_at=datetime(2026, 8, 21, 5, 50, tzinfo=UTC),
        calibration=calibration,
    )
    assert "線型確認：線型同向確認｜放量確認" in alert.text
    assert "歷史校準：62.5%（40筆・初步可信）" in alert.text


def test_incomplete_external_context_stays_explicit_instead_of_inventing_data() -> None:
    missing = ExternalMarketContext(
        tuple(
            ReferenceReading(label, symbol, None, None, None, "unavailable")
            for label, symbol in {
                "標普期貨": "ES=F",
                "那指期貨": "NQ=F",
                "道指期貨": "YM=F",
                "美元台幣": "TWD=X",
            }.items()
        )
    )
    alert = build_session_close_alert(
        payload(), missing, session="afterhours", observed_at=datetime.now(UTC)
    )
    assert "標普期貨：資料不足" in alert.text


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_public_reference_source_is_sanitized_and_failure_is_per_symbol() -> None:
    def opener(request, timeout):
        assert timeout == 3
        if "ES%3DF" in request.full_url:
            body = {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 6500,
                                "chartPreviousClose": 6450,
                                "regularMarketTime": 1787350000,
                            }
                        }
                    ]
                }
            }
            return Response(json.dumps(body).encode())
        raise OSError("offline")

    result = PublicDelayedReferenceSource(opener=opener, timeout_seconds=3).load()
    assert result.reading("標普期貨").change_percent > 0
    assert result.reading("那指期貨").status == "unavailable"
