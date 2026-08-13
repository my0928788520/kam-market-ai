# KAM Five-Timeframe State Mapping v1.0

This contract maps normalized analysis for `5m`, `15m`, `60m`, `1d`, and
`1w` into the existing KAM two-axis state codes. It is deterministic,
market-data-only, and cannot create or submit an order.

## Direction axis

| Axis | Meaning | Rule |
| --- | --- | --- |
| `A` | Bullish | At least one bullish/supportive directional module and no bearish or degraded directional module |
| `B` | Bearish | At least one bearish directional module and no bullish or degraded directional module |
| `N` | Neutral/conflicting | No directional evidence, mixed evidence, or ambiguous/conflicting evidence |

Directional modules are position, trend, and structure. Mixed bullish and
bearish evidence never receives `A` or `B`.

## Lifecycle axis

| Axis | Meaning | Rule |
| --- | --- | --- |
| `U` | Confirmed/usable | Frame is ready, timing is confirmed, usable is true, and there are no error codes |
| `F` | Forming/waiting | Valid analysis exists but confirmation is still provisional or waiting |
| `D` | Degraded/unusable | Unusable, stale, invalid, unavailable, ambiguous, calculation error, or any analysis error code |

Combining both axes produces exactly `AU`, `AF`, `AD`, `NU`, `NF`, `ND`,
`BU`, `BF`, and `BD`.

## Read-only KAM decision

- Weekly and daily `A` alignment may report `偏多`; the unique next step is
  the first unconfirmed timeframe, or manual confirmation when all five are
  `AU`.
- Weekly and daily `B` alignment may report `偏空`, but the current short
  strategy is not approved, so the only action remains `HOLD`.
- Higher-timeframe disagreement, any `D` state, or insufficient analysis
  reports `觀望` with one waiting or recovery step.
- Every output is `OBSERVATION_ONLY`, `market_data_only=true`,
  `live_order_allowed=false`, and `action=HOLD`.
