"""Provider-specific read-only infrastructure adapters.

Provider SDK types must not cross this package boundary into domain models.
"""

from .fubon_futures_runtime import (
    FubonFuturesLiveClient,
    FubonFuturesRuntimeConfig,
    FubonFuturesRuntimeError,
    FubonFuturesRuntimeFailure,
    FubonFuturesRuntimeStatus,
)
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
    "FubonFuturesLiveClient",
    "FubonFuturesRuntimeConfig",
    "FubonFuturesRuntimeError",
    "FubonFuturesRuntimeFailure",
    "FubonFuturesRuntimeStatus",
    "FugleFuturesClientConfig",
    "FugleFuturesClientStatus",
    "FugleFuturesPayloadMapper",
    "FugleFuturesProviderError",
    "FugleFuturesReadOnlyClient",
    "FugleFuturesSymbolRegistry",
]
