# Position Engine Release Note — V3 Sprint 1 Phase 1

## 新增內容

- KAM 專屬離線 `PositionEngineConfig`、單週期 range evaluator 與四週期聚合器。
- 固定 range／data status enum、Decimal 計算、warnings 診斷與 fail-closed 行為。
- Deterministic unit tests 與 Position Engine 規格文件。

## 未修改內容

未修改 Dashboard、API、Position Parser、富邦持倉查詢、憑證、交易／下單、Trend／Structure／Timing／Decision Confidence／AI，亦未修改 `KAM_V1.6_fubon_bridge`。

## 測試結果

新增 Position Engine 測試 23 passed；完整測試集為 120 passed。

## 已知限制

- Config 皆為 PROVISIONAL，尚未經實盤驗證。
- Candle 正式模型沒有 `is_closed`，目前以 `end <= evaluated_at` 推導；上游日夜盤、換月、週線切分與資料延遲語義尚待確認。
- 本版本只有箱型位置，不包含趨勢線、雙重確認、方向判斷或交易行為。

## 下一步

在人工確認 Config 與上游 Candle 語義後，進行 V3 Sprint 1 Phase 2 的獨立趨勢線／pivot 實作；仍須先保持唯讀與離線測試，並取得另行授權後才考慮 API 或 Dashboard 串接。
