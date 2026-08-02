"""Offline, read-only futures-position parsing primitives.

This package deliberately has no Fubon SDK import and no order capability.
"""

from .debug import PositionDebugWriter
from .match import match_mtx_positions
from .models import MatchedPositionReport, NormalizedFuturesPosition, PositionSide, RawPositionCapture
from .normalizer import PositionNormalizer
from .raw import PositionRawAdapter

__all__ = [
    "MatchedPositionReport",
    "NormalizedFuturesPosition",
    "PositionDebugWriter",
    "PositionNormalizer",
    "PositionRawAdapter",
    "PositionSide",
    "RawPositionCapture",
    "match_mtx_positions",
]
