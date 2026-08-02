# Position Engine Specification — V3 Sprint 1 Phase 1

## 目的

Position Engine 是純離線、唯讀的價格箱型位置計算器。它對 15m、60m、1d、1w 分別計算已完成 K 棒形成的 range 與呼叫端提供之 current price 的相對位置。它不做多空判斷、決策評分、趨勢線、結構、時機、風險或交易。

## Input

- `timeframe`：`15m`、`60m`、`1d`、`1w`。
- `candles`：既有正式 `kam_market_ai.models.Candle` 序列。`end` 是 K 棒 timestamp；`end <= evaluated_at` 視為 `is_closed=true`。正式 Candle 尚無 `is_closed` 欄位，因此上游需確保這個時間語義正確。
- `current_price`：有限、正值數字；可代表未完成 K 棒的即時價格。
- `evaluated_at`：有一致時區語義的觀察時間。
- `PositionEngineConfig`：唯一的 V3 Position Engine 設定來源。

## Output 與 Enum

每週期輸出 `PositionRangeResult`：`timeframe`、`range_high`、`range_low`、`range_width`、`current_price`、`position_percent`、`distance_to_high`、`distance_to_low`、`range_state`、`data_status`、`candle_count`、`lookback_used`、`evaluated_at`、`warnings`。

- `range_state`：`breakout_up`、`near_high`、`upper_half`、`middle`、`lower_half`、`near_low`、`breakdown_down`、`insufficient_data`。
- `data_status`：`ok`、`insufficient_data`、`stale`、`invalid`、`calculation_error`。

`evaluate_all_position_ranges` 固定回傳四個 key：`15m`、`60m`、`1d`、`1w`；一個週期失敗不影響其他週期。

## 計算公式

`range_high = max(completed_candle.high)`；`range_low = min(completed_candle.low)`；`range_width = range_high - range_low`。

`position_percent = (current_price - range_low) / range_width * 100`。

`distance_to_high = range_high - current_price`；`distance_to_low = current_price - range_low`。

百分比不限制在 0–100。高於上緣為 `breakout_up`，低於下緣為 `breakdown_down`，兩者優先於所有箱內分類。價格運算使用 `Decimal`。

## K 棒規則與 Fail-closed 行為

- 未完成 K 棒不參與 range high／low；可透過 `current_price` 判斷位置。
- 資料不足回傳 `insufficient_data`；不補造 K 棒。
- NaN、Infinity、非正價格、`high < low`、無效時間、重複 timestamp（預設）均為 `invalid`。
- 時序錯亂僅在 `allow_sort_input=true` 時安全排序並產生 warning；否則為 `invalid`。
- 重複 timestamp 以 Config 的 `reject`、`keep_first` 或 `keep_last` 明確處理。
- range width 小於或等於零為 `invalid`；意外運算錯誤為 `calculation_error` 並保留診斷 warning。
- stale 資料仍保留可重播計算結果，但 `data_status=stale` 並標記 `stale_market_data`，不得視為新鮮行情。

## Config

`PositionEngineConfig.provisional()` 集中以下 **PROVISIONAL** 值，等待實盤驗證：

| 項目 | 15m | 60m | 1d | 1w |
|---|---:|---:|---:|---:|
| lookback | 32 | 24 | 20 | 16 |
| minimum closed candles | 16 | 12 | 10 | 8 |
| stale after | 30 分鐘 | 2 小時 | 2 日 | 14 日 |

箱內門檻為 near low 20、lower half 40、middle 60、upper half 80、near high 100。Config 會驗證所有週期存在、lookback／minimum 合法、stale 時間正值與門檻嚴格遞增；不得用環境變數散落注入。

## 上游／下游責任

上游負責商品、日夜盤、換月、連續合約、時區、週線切分與 Candle 完成狀態的正確性。Position Engine 不建立新規則。下游只能讀取結果；Dashboard、API、Decision、Trend、Structure、Timing、Risk、AI 與交易功能均不在本階段範圍。

## 已確認事項、待確認事項與測試範圍

已確認：四週期隔離、完成 K 棒邊界、Decimal 運算、固定 enum、fail-closed。

待人工確認：provisional lookback／最少根數／stale 門檻、session／夜盤／週線切分、連續合約與換月、資料延遲語義。這些未確認前不得視為交易參數。

測試覆蓋：所有箱內狀態、上下突破、邊界等值、無效 current price／Candle／range、完成 K 棒不足、未完成 K 棒排除、時序錯亂、重複 timestamp、四週期隔離、Config 驗證與 stale。
