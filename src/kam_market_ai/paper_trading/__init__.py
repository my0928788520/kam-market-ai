"""Deterministic, isolated paper-trading safety boundary."""

from .contracts import PAPER_TRADING_CONTRACT_VERSION
from .safety import evaluate_paper_trading_order

__all__ = ["PAPER_TRADING_CONTRACT_VERSION", "evaluate_paper_trading_order"]
