import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from kam_market_ai.candles import CandleBuilder
from kam_market_ai.config import Settings, TRADING_ENABLED, UnsafeConfigurationError
from kam_market_ai.decision import HardGate
from kam_market_ai.execution import ShadowExecutor
from kam_market_ai.models import (Decision, DecisionState, Instrument, MarketContext,
                                  MarketRegime, SessionKind, Side, SignalGrade, Tick)
from kam_market_ai.risk.dashboard import MarginCatalog, MarginRecord, RiskDashboard
from kam_market_ai.session import SessionEngine
from kam_market_ai.storage import ShadowStore


def dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 14, hour, minute, tzinfo=timezone.utc)


def context(**changes: object) -> MarketContext:
    values = dict(instrument=Instrument.MTX, timestamp=dt(1), session=SessionKind.DAY,
                  price=100, opening_price=99, ma20=98, regime=MarketRegime.TREND_UP,
                  taiex_background_available=True, v_reversal_confirmed=True,
                  support_zones=(), resistance_zones=(), facts={"position_confirmed": True})
    values.update(changes)
    return MarketContext(**values)  # type: ignore[arg-type]


class V01Tests(unittest.TestCase):
    def test_trading_is_permanently_disabled(self) -> None:
        self.assertIs(TRADING_ENABLED, False)
        with patch.dict(os.environ, {"TRADING_ENABLED": "True"}):
            with self.assertRaises(UnsafeConfigurationError):
                Settings.load("missing.env")

    def test_sessions_and_sixty_minute_candle(self) -> None:
        engine = SessionEngine()
        self.assertIs(engine.classify(datetime(2026, 7, 14, 9)), SessionKind.DAY)
        self.assertIs(engine.classify(datetime(2026, 7, 14, 16)), SessionKind.NIGHT)
        builder = CandleBuilder(60)
        self.assertIsNone(builder.add(Tick(Instrument.MTX, dt(1, 1), 100, 2)))
        self.assertIsNone(builder.add(Tick(Instrument.MTX, dt(1, 30), 110, 3)))
        candle = builder.add(Tick(Instrument.MTX, dt(2), 105, 1))
        self.assertIsNotNone(candle)
        assert candle is not None
        self.assertEqual((candle.open, candle.high, candle.low, candle.close, candle.volume),
                         (100, 110, 100, 110, 5))

    def test_hard_gate_waits_on_missing_context(self) -> None:
        decision = HardGate().evaluate(context(ma20=None))
        self.assertIs(decision.state, DecisionState.WAIT)
        self.assertIn("MA20_MISSING", decision.reasons)
        self.assertEqual(decision.message, "今日無符合條件訊號，但隨時可能出現訊號。")

    def test_shadow_trade_tracks_excursions_and_storage(self) -> None:
        decision = Decision(DecisionState.ELIGIBLE, SignalGrade.A, (), 4)
        executor = ShadowExecutor()
        trade = executor.enter(decision, Instrument.MTX, Side.LONG, 100, dt(1), 95, 110,
                               "break support")
        trade = executor.mark(trade, 103, dt(1, 5))
        trade = executor.mark(trade, 94, dt(1, 10))
        self.assertEqual((trade.mfe, trade.mae, trade.exit_reason), (3, 6, "STOP"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shadow.db"
            store = ShadowStore(path)
            store.initialize()
            store.save_trade(trade)
            self.assertTrue(path.exists())

    def test_margin_is_updateable_not_hard_coded(self) -> None:
        margins = MarginCatalog()
        self.assertIsNone(margins.get(Instrument.MTX))
        margins.update(MarginRecord(Instrument.MTX, 50000, 40000, dt(1),
                                    "manual verified source"))
        shot = RiskDashboard(margins).snapshot(200000, Instrument.MTX, 20000, 19900, 10)
        self.assertTrue(shot.margin_available)
        self.assertEqual((shot.reserved_margin, shot.risk_percent), (50000, 0.5))


if __name__ == "__main__":
    unittest.main()

