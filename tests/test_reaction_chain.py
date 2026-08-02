import inspect
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from kam_market_ai.analysis.reaction_chain import (
    AlignmentType,
    ClusterEvent,
    EventCluster,
    PriceDirection,
    ReactionChainEngine,
    ReactionClass,
    reaction_statistics,
)
from kam_market_ai.config import TRADING_ENABLED
from kam_market_ai.models import Instrument
from kam_market_ai.storage import ShadowStore


BASE = datetime(2026, 7, 14, 1, tzinfo=timezone.utc)


def event(instrument: Instrument, price: float, baseline: float | None, milliseconds: int | None,
          received_offset_ms: int = 0) -> ClusterEvent:
    return ClusterEvent(
        instrument=instrument,
        price=price,
        baseline_price=baseline,
        exchange_event_at=None if milliseconds is None else BASE + timedelta(milliseconds=milliseconds),
        received_at=BASE + timedelta(milliseconds=received_offset_ms),
    )


def cluster(*events: ClusterEvent) -> EventCluster:
    return EventCluster.from_events(events)


class ReactionChainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ReactionChainEngine()

    def test_full_follow_and_exchange_latency(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 100.1, 100, 0),
            event(Instrument.TX, 200.2, 200, 100),
            event(Instrument.MTX, 300.3, 300, 200),
        ))
        self.assertIs(result.reaction_class, ReactionClass.FULL_FOLLOW)
        self.assertEqual((result.ir_response_latency_ms, result.tx_response_latency_ms, result.tmf_response_latency_ms),
                         (0.0, 100.0, 200.0))
        self.assertTrue(result.response_windows.response_within_250ms)

    def test_partial_follow(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, 10),
            event(Instrument.MTX, 300, 300, 20),
        ))
        self.assertIs(result.reaction_class, ReactionClass.PARTIAL_FOLLOW)
        self.assertIs(result.alignment_type, AlignmentType.PARTIAL_ALIGNMENT)

    def test_no_follow(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 200, 200, 10),
            event(Instrument.MTX, 300, 300, 20),
        ))
        self.assertIs(result.reaction_class, ReactionClass.NO_FOLLOW)
        self.assertIs(result.alignment_type, AlignmentType.DIVERGENCE)

    def test_opposite_response(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 199, 200, 10),
            event(Instrument.MTX, 299, 300, 20),
        ))
        self.assertIs(result.reaction_class, ReactionClass.OPPOSITE_RESPONSE)

    def test_short_transient_alignment(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, 10),
            event(Instrument.MTX, 301, 300, 20), event(Instrument.TX, 202, 200, 500),
            event(Instrument.MTX, 302, 300, 500), event(Instrument.TX, 199, 200, 2_000),
            event(Instrument.MTX, 299, 300, 2_000),
        ))
        self.assertTrue(result.persist_1s)
        self.assertFalse(result.persist_3s)
        self.assertIs(result.alignment_type, AlignmentType.TRANSIENT_ALIGNMENT)

    def test_persistent_alignment(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, 10),
            event(Instrument.MTX, 301, 300, 20), event(Instrument.TX, 202, 200, 500),
            event(Instrument.MTX, 302, 300, 500), event(Instrument.TX, 203, 200, 6_000),
            event(Instrument.MTX, 303, 300, 6_000),
        ))
        self.assertTrue(result.persist_5s)
        self.assertTrue(result.persist_10s)
        self.assertIs(result.alignment_type, AlignmentType.PERSISTENT_ALIGNMENT)

    def test_missing_exchange_timestamp_is_insufficient_and_never_uses_receive_time(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, None, -500),
            event(Instrument.MTX, 301, 300, 20),
        ))
        self.assertIs(result.reaction_class, ReactionClass.INSUFFICIENT_DATA)
        self.assertIsNone(result.tx_response_latency_ms)
        self.assertIsNone(result.response_windows.response_within_1s)

    def test_exchange_order_wins_when_receive_order_is_reverse(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TX, 201, 200, 100, 0),
            event(Instrument.TAIEX, 101, 100, 0, 1_000),
            event(Instrument.MTX, 301, 300, 200, -1_000),
        ))
        self.assertIs(result.trigger_instrument, Instrument.TAIEX)
        self.assertEqual(result.tx_response_latency_ms, 100.0)

    def test_bps_normalizes_different_point_scales(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 100.1, 100, 0),
            event(Instrument.TX, 10_010, 10_000, 10),
            event(Instrument.MTX, 10.01, 10, 20),
        ))
        for change in (result.ir_response_change_bps, result.tx_response_change_bps, result.tmf_response_change_bps):
            self.assertAlmostEqual(change, 10.0, places=9)
        self.assertEqual(result.ir_response_direction, PriceDirection.UP)

    def test_descriptive_statistics_and_no_trading_surface(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, 10),
            event(Instrument.MTX, 301, 300, 20),
        ))
        stats = reaction_statistics([result])
        self.assertEqual(stats["reaction_class_count"], {"FULL_FOLLOW": 1})
        self.assertIs(TRADING_ENABLED, False)
        source = inspect.getsource(__import__("kam_market_ai.analysis.reaction_chain", fromlist=["*"]))
        self.assertNotIn("FubonSDK", source)
        self.assertNotIn("FutOptOrder", source)

    def test_reaction_analysis_is_stored_as_an_observation_only(self) -> None:
        result = self.engine.analyze(cluster(
            event(Instrument.TAIEX, 101, 100, 0), event(Instrument.TX, 201, 200, 10),
            event(Instrument.MTX, 301, 300, 20),
        ))
        with tempfile.TemporaryDirectory() as directory:
            store = ShadowStore(f"{directory}/observations.db")
            store.initialize()
            store.save_reaction_analysis(result, BASE.isoformat())
            self.assertTrue(store.path.exists())


if __name__ == "__main__":
    unittest.main()
