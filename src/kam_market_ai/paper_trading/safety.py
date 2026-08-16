"""Pure risk evaluation for isolated Paper Trading requests."""
from __future__ import annotations

from .contracts import (
    PAPER_TRADING_CONTRACT_VERSION,
    PaperTradingAuditEvent,
    PaperTradingOrderRequest,
    PaperTradingOrderResult,
    PaperTradingOrderState,
    PaperTradingSafetyState,
)


def _reject(request: PaperTradingOrderRequest, *codes: str) -> PaperTradingOrderResult:
    return PaperTradingOrderResult(request.idempotency_key, PaperTradingOrderState.REJECTED, tuple(sorted(set(codes))), request.request_hash, request.created_at)


def evaluate_paper_trading_order(request: PaperTradingOrderRequest, state: PaperTradingSafetyState) -> PaperTradingOrderResult:
    """Evaluate one paper request deterministically; no order is sent anywhere."""
    if not isinstance(request, PaperTradingOrderRequest) or not isinstance(state, PaperTradingSafetyState):
        raise ValueError("Unsupported Paper Trading safety input type.")
    codes: list[str] = []
    if request.request_version != PAPER_TRADING_CONTRACT_VERSION: codes.append("INVALID_VERSION")
    if request.created_at.tzinfo is None or request.created_at.utcoffset().total_seconds() != 0: codes.append("INVALID_TIMESTAMP")
    if not state.paper_trading_enabled: codes.append("PAPER_TRADING_DISABLED")
    if state.emergency_stop: codes.append("EMERGENCY_STOP")
    if request.idempotency_key in state.used_idempotency_keys: codes.append("DUPLICATE_IDEMPOTENCY_KEY")
    if state.account_snapshot is None or state.risk_limits is None: codes.append("SAFETY_CONTEXT_MISSING")
    if codes: return _reject(request, *codes)
    account = state.account_snapshot; limits = state.risk_limits
    if request.instrument not in limits.allowed_instruments: codes.append("INSTRUMENT_NOT_ALLOWED")
    if request.quantity > limits.max_order_quantity: codes.append("MAX_ORDER_QUANTITY_EXCEEDED")
    if request.instrument.startswith("TMF"):
        current = next(
            (position.quantity for position in account.positions if position.instrument == request.instrument),
            0,
        )
        signed_quantity = request.quantity if request.side.value == "buy" else -request.quantity
        if request.quantity > 1 or abs(current + signed_quantity) > 1:
            codes.append("ONE_MICRO_TAIWAN_CONTRACT_LIMIT")
    if request.quantity * request.price > limits.max_notional: codes.append("MAX_NOTIONAL_EXCEEDED")
    if account.daily_realized_pnl <= -limits.max_daily_loss: codes.append("MAX_DAILY_LOSS_EXCEEDED")
    existing = {position.instrument for position in account.positions}
    if request.instrument not in existing and len(existing) >= limits.max_open_positions: codes.append("MAX_OPEN_POSITIONS_EXCEEDED")
    if request.created_at.weekday() not in limits.allowed_weekdays or not limits.session_start <= request.created_at.timetz().replace(tzinfo=None) < limits.session_end: codes.append("TRADING_SESSION_NOT_ALLOWED")
    if codes: return _reject(request, *codes)
    return PaperTradingOrderResult(request.idempotency_key, PaperTradingOrderState.ACCEPTED, (), request.request_hash, request.created_at)


def build_paper_trading_audit_event(result: PaperTradingOrderResult) -> PaperTradingAuditEvent:
    if not isinstance(result, PaperTradingOrderResult): raise ValueError("Unsupported Paper Trading result type.")
    return PaperTradingAuditEvent("order_accepted" if result.state is PaperTradingOrderState.ACCEPTED else "order_rejected", result.request_hash, result.result_hash, result.evaluated_at, result.reason_codes)
