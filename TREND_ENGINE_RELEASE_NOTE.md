# Trend Engine Release Note — V3 Sprint 1 Phase 2

## 新增內容

- KAM 專屬 `pivot_detector.py`：confirmed pivot high／low 與 plateau policy。
- KAM 專屬 `trend_engine.py`：ascending／descending candidate、時間斜率、projection、tolerance、touch、violation、break、retest、rejection、候選選擇與四週期聚合。
- 離線 deterministic Pivot／Trend Engine 測試與正式規格文件。

## 未修改內容

未修改 Position Engine、Dashboard、API、Position Parser、富邦持倉查詢、憑證、下單、Structure／Timing／Decision Confidence／Risk／AI 或 `KAM_V1.6_fubon_bridge`。

## 測試結果

新增 Pivot／Trend Engine 測試 18 passed；完整測試集為 138 passed。

## 已知限制

- 所有 Config 都是 PROVISIONAL，未經實盤驗證。
- Candle 完成狀態目前由 `end <= evaluated_at` 推導；上游 session、夜盤、換月、連續合約、週線邊界與資料延遲仍待確認。
- 沒有 Structure Engine、箱型／趨勢雙重確認、決策或任何交易行為。

## 下一步

在人工確認 provisional Config 與 Candle 語義後，最小後續 Sprint 可建立 Structure Engine 的獨立資料契約；需先維持離線、唯讀與 fail-closed，且另行授權後才能串接 API 或 Dashboard。
