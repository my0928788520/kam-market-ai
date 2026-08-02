# 第一階段執行計畫

## 空明 KAM｜台灣期貨 Market Foundation V0.1

正式名稱為「空明 KAM｜Market Research OS」，定位為 Market Research Operating System（市場研究作業系統）。核心流程：Reality → Observation → Evidence → Knowledge → Decision。Decision 僅保留未來架構位置，未啟用；交易只是未來可能輸出，不是目前核心。`RESEARCH_MODE=True`、`TRADING_ENABLED=False`。

> 🛜 空明真正的資產，是體驗後的智慧，不是程式。

本專案之研究架構、資料模型、觀察流程、知識演化設計與實證資料，屬空明原創智慧資產。公開內容與核心實作應分層管理。不得公開真實 `.env`、登入資料、憑證資料、token、核心實證資料庫、尚未決定公開的研究規則或完整私有 Prompt / Workflow。

1. 固定資料字典：確認 TAIEX、TX、MTX 官方商品代碼、交易日曆與時區規則。
2. 在隔離分支依官方 SDK 文件補齊「唯讀行情」adapter，先以錄製資料驗證。
3. 建立 session-aligned 60K（處理 08:45、15:00 與跨午夜）及缺漏資料政策。
4. 將開盤位置、20MA、支撐壓力、盤整、V 轉轉成有版本的規則參數。
5. 以歷史 replay 驗證 Hard Gate、No Trade reasons 與 A/A+，不追求訊號數量。
6. 完成 Shadow 日誌、MFE/MAE、原因失效與修正延遲統計。
7. 匯入經人工確認且帶日期/來源的最新保證金，驗證風險儀表板。
8. 定義觀察期、樣本外檢查與規則變更紀錄；V0.1 持續禁止真實委託。
