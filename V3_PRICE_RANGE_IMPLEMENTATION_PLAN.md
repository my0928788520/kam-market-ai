# V3 價格區間與雙重趨勢線確認實作計畫

## 1. 目的與本輪邊界

V3 將在 **15 分、60 分、日線、週線** 各自計算箱型位置與趨勢線，並輸出一個不強行偏多或偏空的雙重確認結果。

本文件是規格與實作計畫，不是程式變更。本輪不得修改 Position Parser、富邦持倉查詢、Dashboard、既有 API、下單或任何交易功能；也不得修改或引用 `KAM_V1.6_fubon_bridge`。

本計畫不搬用 KAM Stock 的趨勢線、Schema、欄位、規則或測試。KAM 專案將有獨立的資料契約、命名與測試 fixture。

## 2. 資料來源與週期隔離

### 2.1 唯一輸入資料契約

每一週期輸入為同一商品、時間遞增的 OHLCV Candle 序列，至少包含：

- `start`、`end`、`open`、`high`、`low`、`close`、`volume`
- `is_completed: bool`（或可由 `end <= observation_time` 明確推導）
- `observation_time`：本次計算觀察時間

資料可由既有 `MarketDataProvider.historical_candles` 的未來實作或可重播 fixture 提供；本階段不指定或新增任何 broker／行情 API。使用前須先驗證時區、交易日切分、週線切分、缺 K 棒補法與價格單位。

### 2.2 四個獨立計算域

| 週期 | Candle 間隔 | 箱型與 pivot 輸入 | 趨勢線 | 不可共用項目 |
|---|---:|---|---|---|
| 15 分 | 15 分鐘 | 僅 15 分序列 | 僅 15 分 pivot | 錨點、斜率、觸碰、失效狀態 |
| 60 分 | 60 分鐘 | 僅 60 分序列 | 僅 60 分 pivot | 同上 |
| 日線 | 交易日 | 僅日線序列 | 僅日線 pivot | 同上 |
| 週線 | 交易週 | 僅週線序列 | 僅週線 pivot | 同上 |

四個週期不得共用同一條趨勢線、anchor points、lookback 視窗或確認計數。跨週期畫面可並列，但不得把高週期線投射成低週期計算結果。

## 3. 每週期輸出契約

### 3.1 箱型位置（range）

每個週期必須輸出：

```json
{
  "range_high": "Decimal | null",
  "range_low": "Decimal | null",
  "current_price": "Decimal | null",
  "position_percent": "Decimal | null",
  "distance_to_high": "Decimal | null",
  "distance_to_low": "Decimal | null",
  "range_state": "at_low | inside | at_high | breakout_up | breakdown_down | insufficient_data"
}
```

計算規則：

- `range_high`：lookback 內**完成 K 棒**的最高 `high`。
- `range_low`：lookback 內**完成 K 棒**的最低 `low`。
- `current_price`：可使用最新未完成 K 棒的 `close`；若無未完成 K 棒，使用最後一根完成 K 棒 `close`。必須標示 observation time，不能假裝是即時行情。
- `position_percent = (current_price - range_low) / (range_high - range_low) * 100`；零寬區間、缺資料或無法比較時為 `null`。
- `distance_to_high = range_high - current_price`；`distance_to_low = current_price - range_low`。
- `at_low`、`at_high` 使用容許誤差判定；`inside` 指其餘仍在箱內的位置。
- `breakout_up`、`breakdown_down` 必須通過第 6 節的 break confirmation；未確認不得輸出突破／跌破。

### 3.2 趨勢線（trendline）

每個週期必須輸出：

```json
{
  "active_trendline_type": "ascending | descending | none",
  "anchor_points": [{"index": 0, "timestamp": "ISO-8601", "price": "Decimal"}],
  "anchor_count": 0,
  "touch_count": 0,
  "slope": "Decimal | null",
  "current_trendline_value": "Decimal | null",
  "distance_to_trendline": "Decimal | null",
  "relation_to_trendline": "above | below | touching | breakout_up | breakdown_down | retest | rejection | insufficient_data",
  "last_touch_at": "ISO-8601 | null",
  "broken": false,
  "confidence": "Decimal | null",
  "trendline_state": "ascending_valid | descending_valid | ascending_broken | descending_broken | none | insufficient_data"
}
```

`anchor_points` 保留原始 Candle index、時間及價格；價格、距離與斜率使用 `Decimal`，不得以 float 累積運算。

## 4. Pivot 判定與有效高低點

### 4.1 共通 pivot 方案

對每一週期獨立執行。候選 Candle 必須是完成 K 棒，且其左右兩側用於確認的 Candle 也必須完成：

- **pivot low**：候選的 `low` 小於或等於左右確認窗內所有低點；若同價，使用較早的 Candle 作為唯一 pivot，避免重複錨點。
- **pivot high**：候選的 `high` 大於或等於左右確認窗內所有高點；若同價，使用較早的 Candle 作為唯一 pivot。
- 未完成 K 棒絕不可作為 pivot 或 anchor；它只能用於第 6 節的目前價格相對趨勢線判斷。
- 不完整、無序、重複 timestamp、價格不合法或缺 `is_completed` 資訊的輸入，必須輸出 `insufficient_data` 或異常原因，不可補造 pivot。

### 4.2 各週期如何找有效高低點

四個週期皆採 4.1 演算法，但以各自的 `left_pivot_bars`、`right_pivot_bars`、`lookback_bars` 與最小錨點間距獨立設定：

| 週期 | 有效低點 | 有效高點 | Lookback／左右確認窗 |
|---|---|---|---|
| 15 分 | 15 分完成 K 棒的 pivot low | 15 分完成 K 棒的 pivot high | **待人工確認** |
| 60 分 | 60 分完成 K 棒的 pivot low | 60 分完成 K 棒的 pivot high | **待人工確認** |
| 日線 | 日線完成 K 棒的 pivot low | 日線完成 K 棒的 pivot high | **待人工確認** |
| 週線 | 週線完成 K 棒的 pivot low | 週線完成 K 棒的 pivot high | **待人工確認** |

不得用同一組固定 lookback 數字套用全部週期。具體根數是關鍵交易參數，尚未確認前不得自行設定預設值；實作應要求明確 Config 或在缺設定時回傳 `insufficient_data`。

## 5. 趨勢線建立

### 5.1 上升趨勢線

- 僅可從同週期的完成 K 棒 pivot low 建立。
- 至少需要兩個有效低點。
- 第二個低點必須嚴格高於第一個低點；不符合時不可稱為上升趨勢線。
- 候選錨點依時間遞增，且間距須符合該週期的 `minimum_anchor_separation_bars`（待人工確認）。
- 優先使用最近、仍未失效的有效 higher-low 錨點組；選擇規則必須可追溯，不可因結果偏多而挑選較有利組合。

### 5.2 下降趨勢線

- 僅可從同週期的完成 K 棒 pivot high 建立。
- 至少需要兩個有效高點。
- 第二個高點必須嚴格低於第一個高點；不符合時不可稱為下降趨勢線。
- 其餘選擇、可追溯與間距規則比照上升線，但使用 lower-high 錨點。

### 5.3 線值與斜率

以 anchor index 作為等距 bar 座標：

`slope = (price_2 - price_1) / (index_2 - index_1)`

`current_trendline_value = price_1 + slope * (current_index - index_1)`

若 index 不遞增、兩 anchor 同 index、時間不連續而無法確認 bar 座標，趨勢線輸出 `none`／`insufficient_data`。不以跨週期時間差或未標準化交易時段替代計算。

## 6. 觸碰、突破、回踩與失效

### 6.1 容許誤差與有效觸碰

`touch_tolerance` 必須由每週期的 Config 明確提供，可採點數或百分比，但單位不得混用。未確認前不設定數值。

- 有效觸碰：完成 K 棒的相關極值（上升線用 `low`、下降線用 `high`）與線值絕對距離不超過 `touch_tolerance`，且不構成已確認反向 break。
- `touch_count`：不計兩個 anchor 的話，額外有效觸碰數；實作必須同時保留「含 anchor／不含 anchor」的定義，並在 payload 文件中固定其中一種。V3 預設 payload 為**不含 anchor**。
- `last_touch_at`：最近一個有效觸碰的完成 K 棒結束時間。

### 6.2 relation_to_trendline

| 值 | 判定 |
|---|---|
| `above` | 目前價格高於線值且超過誤差，未通過 breakout 條件 |
| `below` | 目前價格低於線值且超過誤差，未通過 breakdown 條件 |
| `touching` | 目前價格與線值差距在誤差內 |
| `breakout_up` | 向上穿越趨勢線，且完成 K 棒符合真突破確認 |
| `breakdown_down` | 向下跌破趨勢線，且完成 K 棒符合真跌破確認 |
| `retest` | 已確認突破／跌破後回到誤差帶，且尚未出現反向確認 break |
| `rejection` | 在誤差帶有效觸碰後，完成 K 棒朝原側離開，且未通過穿越確認 |
| `insufficient_data` | 無有效線、資料／設定不足或輸入異常 |

未完成 K 棒可用於 `above`、`below`、`touching` 的目前位置；不可單獨觸發 `breakout_up`、`breakdown_down`、`retest`、`rejection`、touch_count 或 broken。

### 6.3 假突破、真突破、跌破、回踩與反壓

- **真突破**：完成 K 棒收盤在趨勢線上方超過 `break_tolerance`，連續 `break_confirmation_bars` 根完成 K 棒仍滿足條件。
- **真跌破**：完成 K 棒收盤在線下方超過 `break_tolerance`，連續 `break_confirmation_bars` 根完成 K 棒仍滿足條件。
- **假突破／假跌破**：曾穿越誤差帶但未完成上述確認，或在確認根數內回到原側；不得標為 breakout／breakdown。
- **回踩（retest）**：已確認向上突破後，價格回到線的誤差帶且未完成向下跌破；下降線的反向情況同理。
- **反壓（rejection）**：下降線附近觸碰後無法向上確認突破並向下離開；上升線附近的對稱情況稱為支撐反應，仍以 `rejection` 表示，並由 `active_trendline_type` 解讀方向。

`break_tolerance` 與 `break_confirmation_bars` 為關鍵參數，四週期皆須人工確認，未確認即輸出 `insufficient_data`，不得以臨時常數取代。

### 6.4 趨勢線失效

- 上升線：完成 K 棒符合真跌破條件時 `broken=true`、`trendline_state=ascending_broken`。
- 下降線：完成 K 棒符合真突破條件時 `broken=true`、`trendline_state=descending_broken`。
- 因新的 pivot 導致需重建候選線時，舊線保留為歷史診斷資料；不得靜默覆蓋並改寫既有訊號。
- 沒有兩個有效錨點、缺關鍵參數、資料不足或計算異常時，不宣稱線已失效，而是 `active_trendline_type=none`、`trendline_state=insufficient_data`。

### 6.5 confidence

`confidence` 是 0–1 的可追溯 Decimal，不是模型機率。未完成以下人工確認前一律 `null`：

- anchor_count、touch_count、最近觸碰距離、資料完整度、break 狀態各自的權重；
- 最低 confidence 門檻；
- 不同週期是否採不同權重。

## 7. 箱型與趨勢線雙重確認

### 7.1 訊號正規化

- 箱型多方證據：`range_state=breakout_up`。
- 箱型空方證據：`range_state=breakdown_down`。
- 趨勢線多方證據：有效上升線且 `relation_to_trendline` 為 `above`、`touching` 或確認後的 `retest`，且 `broken=false`。
- 趨勢線空方證據：有效下降線且 `relation_to_trendline` 為 `below`、`touching` 或確認後的 `retest`，且 `broken=false`。
- `at_low`、`at_high`、`inside`、`rejection` 不單獨宣告多空；它們是位置／行為描述，避免以箱底或箱頂猜測方向。

### 7.2 固定輸出與決策表

`dual_confirmation` 僅能是下列值：

| 箱型訊號 | 趨勢線訊號 | 輸出 |
|---|---|---|
| 多方 | 多方 | `bullish_confirmed` |
| 空方 | 空方 | `bearish_confirmed` |
| 多方 | 中性 | `bullish_range_only` |
| 空方 | 中性 | `bearish_range_only` |
| 中性 | 多方 | `bullish_trendline_only` |
| 中性 | 空方 | `bearish_trendline_only` |
| 多方 | 空方，或空方 | 多方 | `conflict` |
| 中性 | 中性 | `neutral` |
| 任一側資料／關鍵設定不足 | 任意 | `insufficient_data` |

衝突時必須輸出 `conflict`；不得以較高週期、較高 confidence、最近訊號或任何未被授權的偏好強行選擇多方或空方。

## 8. 未來 API Payload（提案，非本輪 API 變更）

未來可在新的唯讀市場結構 endpoint 或既有 dashboard payload 的**明確版本化擴充**中提供：

```json
{
  "instrument": "MTX",
  "observation_time": "ISO-8601",
  "timeframes": {
    "15m": {"range": {}, "trendline": {}, "dual_confirmation": "insufficient_data", "diagnostics": []},
    "60m": {"range": {}, "trendline": {}, "dual_confirmation": "insufficient_data", "diagnostics": []},
    "1d":  {"range": {}, "trendline": {}, "dual_confirmation": "insufficient_data", "diagnostics": []},
    "1w":  {"range": {}, "trendline": {}, "dual_confirmation": "insufficient_data", "diagnostics": []}
  }
}
```

每個 `range` 與 `trendline` 的欄位必須完全符合第 3 節。`diagnostics` 僅寫可安全公開的資料品質與設定缺失原因，不含帳戶、憑證、token 或任何個資。

## 9. 未來前台顯示方式（非本輪 Dashboard 變更）

- 五週期列每格顯示：週期、`range_state`、`relation_to_trendline`、`dual_confirmation` 與資料不足原因。
- 市場轉折位置圖顯示灰色箱體／趨勢線與 anchor；資料不足時顯示「資料不足，位置尚未建立」，不繪製虛構線。
- `conflict` 必須以中性警示呈現，不可使用多方或空方顏色暗示結論。
- `insufficient_data` 與資料異常必須與「neutral」視覺區隔。
- 本計畫不新增即時行情、AI 摘要、交易操作或背景高頻輪詢。

## 10. 測試案例

所有測試使用 KAM 專屬合成 Candle fixtures，不依賴 KAM Stock、真實帳戶或真實行情。

1. 四週期各自計算，驗證 anchor、slope、touch_count 不跨週期共享。
2. 箱型 high／low、position_percent、兩側距離及零寬箱型。
3. 上升線：兩個完成且遞增的有效低點可建立。
4. 下降線：兩個完成且遞減的有效高點可建立。
5. 第二低點未高於第一低點、第二高點未低於第一高點時拒絕建立。
6. 未完成 K 棒不可成為 pivot／anchor，但可改變 current price 的 above／below／touching。
7. 有效觸碰、重複同價 pivot 去重、最後觸碰時間。
8. 真突破／真跌破、假突破／假跌破、回踩、反壓及失效。
9. range 多方＋trendline 空方及其反向組合必為 `conflict`。
10. 六種單側／雙側／中性結果與 `insufficient_data` 決策表全覆蓋。
11. 缺 Candle、亂序 timestamp、缺完成狀態、非法價格、缺 Config 皆 fail closed。
12. Decimal 精度：不使用 float 累積後產生錯誤距離或斜率。
13. payload schema、JSON 序列化與前台資料不足顯示（待前台串接階段）。

## 11. 資料不足與異常狀態

以下情況必須輸出 `insufficient_data`，並在 diagnostics 記錄可讀原因：

- 有效完成 K 棒不足以形成 lookback、pivot 或兩個錨點；
- 任一關鍵 Config 未經人工確認；
- 交易週／日切分、時區、價格單位或資料來源品質未確認；
- 箱型寬度為零、Candle 無序／重複／欄位缺失／價格非法；
- 趨勢線 index 或錨點無法計算；
- 資料延遲超出未來定義的 staleness 門檻。

資料不足不是中性：不得輸出 `neutral` 來掩蓋缺資料，也不得回退到假定的多空趨勢。

## 12. 必須人工確認的參數

| 參數 | 需確認內容 |
|---|---|
| lookback_bars | 15m、60m、1d、1w 各自根數 |
| left/right pivot bars | 各週期 pivot 左右確認窗 |
| minimum_anchor_separation_bars | 兩錨點最低間隔 |
| touch_tolerance | 點數或百分比、各週期數值與單位 |
| break_tolerance | 突破／跌破最小穿越幅度 |
| break_confirmation_bars | 真 break 所需完成 K 棒數 |
| weekly/session boundary | 週線起訖、夜盤歸屬、交易日與時區 |
| current_price 定義 | 最新未完成 K 棒 close 的資料延遲門檻 |
| confidence 權重 | 各品質項目與最小門檻 |

任一項未確認時，實作不得猜測常數或產生正式 directional signal。

## 13. 預計新增與修改檔案（未來實作階段）

| 動作 | 檔案 | 責任 |
|---|---|---|
| 新增 | `src/kam_market_ai/analysis/price_range_contracts.py` | KAM 專屬 range、trendline、雙重確認資料模型與 enum |
| 新增 | `src/kam_market_ai/analysis/price_range.py` | 完成 K 棒箱型位置、距離與 range state |
| 新增 | `src/kam_market_ai/analysis/trendline.py` | pivot、anchor、觸碰、突破、失效與趨勢線輸出 |
| 新增 | `src/kam_market_ai/analysis/dual_confirmation.py` | 第 7 節唯一的決策表實作 |
| 新增 | `src/kam_market_ai/analysis/timeframe_structure.py` | 四個完全獨立週期的 orchestrator 與 diagnostics |
| 新增 | `tests/test_price_range.py` | 箱型與資料不足測試 |
| 新增 | `tests/test_trendline.py` | pivot、趨勢線、突破與 Decimal 測試 |
| 新增 | `tests/test_dual_confirmation.py` | 固定決策表與 conflict 測試 |
| 新增 | `tests/fixtures/market_structure/` | KAM 專屬合成 OHLCV fixtures |
| 條件式修改 | `src/kam_market_ai/market_data/base.py` | 僅在確認既有介面不能明確提供完成狀態、日／週切分時才擴充 |
| 條件式修改 | `src/kam_market_ai/dashboard/payload.py`、`dashboard/app.py`、CSS 與 Dashboard tests | 僅在另行授權的前台串接階段使用版本化 payload 顯示 |

不得修改 `positions/`、`tools/probe_fubon_position.py`、任何憑證設定、下單／execution 模組，或 `KAM_V1.6_fubon_bridge`。

## 14. 最小交付順序

1. 先完成第 12 節人工參數確認與 Candle 完成狀態／交易日語義驗證。
2. 新增純離線 contracts 與 fixture，先做箱型位置及資料不足 fail-closed 測試。
3. 實作獨立 pivot 與單週期趨勢線，完成觸碰／break／失效測試。
4. 實作四週期 orchestrator，驗證無共用趨勢線或錨點。
5. 實作雙重確認表與 conflict 保護。
6. 先以唯讀、可重播 payload 驗證；不接 Dashboard。
7. 僅在另行授權後，再新增版本化 API／前台顯示與相對測試。
