"""Provider-specific read-only infrastructure adapters.

Provider SDK types must not cross this package boundary into domain models.
"""

from .fugle_futures_client import (
    FakeFugleFuturesTransport,
    FugleFuturesClientConfig,
    FugleFuturesClientStatus,
    FugleFuturesPayloadMapper,
    FugleFuturesProviderError,
    FugleFuturesReadOnlyClient,
    FugleFuturesSymbolRegistry,
)

__all__ = [
    "FakeFugleFuturesTransport",
    "FugleFuturesClientConfig",
    "FugleFuturesClientStatus",
    "FugleFuturesPayloadMapper",
    "FugleFuturesProviderError",
    "FugleFuturesReadOnlyClient",
    "FugleFuturesSymbolRegistry",
]
