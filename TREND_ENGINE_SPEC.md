# Trend Engine Specification — V3 Sprint 1 Phase 2

## 目的與非目標

Trend Engine 是 KAM 專屬、離線、唯讀、可重播的趨勢線基礎層。它只回答：目前價格相對於有效上升或下降趨勢線處於何種狀態。

本階段不做箱型、W／M、HH／HL／LH／LL 結構總結、頸線、多週期結論、Decision Confidence、Risk、Timing、Next Step、AI、API、Dashboard 或交易。它不使用 KAM Stock 的 schema、規則、Config 或測試。

## Input 與完成 K 棒

輸入為 `timeframe`、既有正式 `Candle` 序列、`current_price`、`evaluated_at` 與 `TrendEngineConfig`。沿用 `Candle.start/end/open/high/low/close`；完成 K 棒固定定義為 `candle.end <= evaluated_at`。未完成 K 棒不能成為 pivot、anchor 或正式 break confirmation，只能由呼叫端提供的 `current_price` 反映目前位置。

上游負責資料來源、時區、交易日／夜盤、週線、換月、連續合約與 Candle 完成語義。Trend Engine 不擅自建立這些規則。

## Pivot 定義

`Pivot` 固定欄位：`pivot_type`、`timeframe`、`candle_index`、`timestamp`、`price`、`left_window`、`right_window`、`confirmed`、`source_candle_end`、`warnings`。

- `pivot_high`：候選 high 符合左右完成 K 棒視窗。
- `pivot_low`：候選 low 符合左右完成 K 棒視窗。
- 右側確認窗不足時不輸出 pivot；不使用未來或未完成 K 棒補足。
- plateau 由 `PlateauPolicy` 控制：`strict`、`first`、`last`、`reject_plateau`；預設 `reject_plateau` 為 **PROVISIONAL**。

## Ascending／Descending 趨勢線

- 上升線使用兩個已確認 `pivot_low`；第二個時間較晚、價格較高，且 slope 大於零。
- 下降線使用兩個已確認 `pivot_high`；第二個時間較晚、價格較低，且 slope 小於零。
- 最小 anchor 間隔、最大 anchor 年齡、最小／最大絕對斜率、觸碰、違規與 stale 均在選線前檢查。
- 時間斜率不使用 Candle index：`slope_per_second = (anchor_2.price - anchor_1.price) / seconds(anchor_2.timestamp - anchor_1.timestamp)`。
- 投影：`value(t) = anchor_1.price + slope_per_second * seconds(t - anchor_1.timestamp)`。

## Output 與固定 Enum

`TrendlineResult` 輸出：`timeframe`、`active_trendline_type`、`anchor_1`、`anchor_2`、`slope_per_second`、`projected_value_at_evaluated_at`、`current_price`、`distance_to_trendline`、`distance_percent`、`relation_to_trendline`、`touch_count`、`violation_count`、`last_touch_at`、`created_at`、`valid`、`confidence`、`trend_state`、`data_status`、`candle_count`、`lookback_used`、`evaluated_at`、`warnings`。

- active type：`ascending`、`descending`、`none`、`ambiguous`。
- relation：`above`、`below`、`touching`、`breakout_up`、`breakdown_down`、`retest`、`rejection`、`insufficient_data`、`ambiguous`、`invalid`。
- trend state：`ascending_supported`、`ascending_broken`、`ascending_retest`、`descending_resisted`、`descending_broken`、`descending_retest`、`no_valid_trendline`、`ambiguous`、`insufficient_data`、`stale`、`invalid`、`calculation_error`。

`confidence` 是候選線的內部品質值，不是 Decision Confidence 或交易分數。

## Tolerance、Touch、Violation、Break、Retest、Rejection

`ToleranceMode` 支援 `fixed_points`、`percentage`、`candle_range_fraction`，所有數值由 Config 提供。

- touch：anchor 後完成 K 棒的上升線 low／下降線 high 位於投影線 ± tolerance；anchor 本身不計入 touch_count。
- violation：完成 K 棒依 break source 落在反側超過 tolerance。
- confirmed break：使用 Config 指定的完成 K 棒 `close` 或 `high_low`，連續滿足 `break_confirmation_bars`。`current_price` 不可完成正式 break。
- ascending 的 confirmed break 為 `breakdown_down`；descending 的 confirmed break 為 `breakout_up`。
- retest：confirmed break 後，在 `retest_max_bars` 內回到原線 tolerance 範圍。
- rejection：break 後已有 retest touch，且又回到原 break 側。

## Candidate Selection、Ambiguity 與失效

所有可行 anchor pair 都先建立 candidate；不能只取最近兩個 pivot。候選品質為可追溯的 provisional 組合：recency、post-anchor touch_count、violation_count、anchor separation 與 slope validity。最高品質候選若與次高候選分差不大於 `ambiguity_score_gap`，輸出 `ambiguous`，不任意選線。

confirmed break、violation_count 超限、anchor 間距／年齡不合格、斜率不合法、來源 invalid 或 stale 都會讓有效性 fail closed。舊線若 broken，會保留其 anchor、break state 與 warnings；不靜默重畫。

## Config（PROVISIONAL）

`TrendEngineConfig` 是唯一 typed Config，包含 lookback、minimum closed candles、pivot windows、plateau policy、anchor separation／age、tolerance、break source／bars、retest、violation／touch、stale、排序、重複 timestamp、ambiguity 與 slope／候選權重。

| 週期 | lookback | 最少完成 K | pivot L/R | 最小 anchor 間隔 | break bars | retest bars |
|---|---:|---:|---:|---:|---:|---:|
| 15m | 64 | 32 | 2/2 | 4 | 2 | 8 |
| 60m | 48 | 24 | 2/2 | 3 | 2 | 6 |
| 1d | 60 | 30 | 2/2 | 3 | 2 | 5 |
| 1w | 52 | 26 | 2/2 | 2 | 1 | 4 |

預設 tolerance 為 `percentage=0.10`，且所有值都是 **PROVISIONAL**，不代表交易規則定案。

## Fail-closed、資料驗證與責任邊界

NaN／Infinity、非正價格、`high < low`、open 或 close 超出 high-low、zero-duration、overlap、時區 aware／naive 混用、未授權排序、未處理重複 timestamp 都回傳 `invalid`。排序只在 `allow_sort_input=true` 時執行且留下 warning。資料不足、無候選線、stale 與 calculation error 都有固定 enum，絕不以自由文字偽裝成功。

`evaluate_all_trendlines` 固定輸出 15m、60m、1d、1w。任何週期的錯誤只影響該週期；不使用其他週期的 anchor、資料或結果替代。

## 待人工確認與測試範圍

待確認：所有 provisional lookback／stale／tolerance／break／retest／anchor age／slope bounds／候選權重，及上游交易時段、週線、連續合約與資料延遲語義。

測試覆蓋 confirmed pivot、plateau、左右窗不足、ascending／descending、投影、above／below／touching、break、retest、rejection、touch／violation、ambiguity、stale、invalid candle、timezone、overlap、重複 timestamp、未完成 K 棒、Config 與四週期隔離。所有測試離線、deterministic，沒有網路、富邦 SDK 或即時時間依賴。
