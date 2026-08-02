# 空明期貨 KAM｜Research OS

## 空明期貨 KAM｜Market Foundation V0.1

私人、非商業、不可供他人使用的 Market Research Operating System（市場研究作業系統）。

Reality → Observation → Evidence → Knowledge → Decision。Decision 目前只保留未來架構位置，未啟用；交易只是未來可能輸出，不是目前核心。

> 盲目的因，造就盲目的果。  
> 控制能控制的，改變能改變的，及時止損，允許結果發生，讓事實成為事實。

系統以「因 → 條件 → 行為 → 結果 → 修正」為核心。條件不足就是 `WAIT`，不為了產生訊號降低門檻：

> 今日無符合條件訊號，但隨時可能出現訊號。

## 安全聲明

- `TRADING_ENABLED` 永久固定為 `False`；設定為其他值會拒絕啟動。
- `RESEARCH_MODE` 固定為 `True`。
- 只有 Shadow 模擬，專案沒有真實委託 gateway、委託模型或下單方法。
- 富邦 Neo V0.1 只有行情抽象介面與未實作 adapter，不登入、不讀憑證、不猜 SDK 方法。
- 帳密、身分資料、憑證密碼、API Key/Secret 只能放在本機環境或 `.env`；`.env` 已忽略。
- `.env.example` 只放空白欄位名稱，不能填入真實秘密後提交。

## 目前範圍

V0.1 已提供 TAIEX/TX/MTX 正規化模型、日夜盤分類、60 分 K 聚合、20MA、動態支撐壓力、趨勢/盤整與 V 轉分析原語、Hard Gate、WAIT/No Trade reasons、A/A+、Cause Health、單口 MTX Shadow 進出、即時停損、MFE/MAE、修正延遲、可更新保證金、資金風險快照、日誌、SQLite 儲存及 replay provider 介面。

### Cross-Market Reaction Timeline V0.2

`analysis.reaction_chain` 只保存 TAIEX、TX、MTX cluster 的描述性反應資料：交易所事件時間、KAM 接收時間、bps 變化、反應延遲、Response Window、Persistence 與 Alignment Type。cluster 的第一筆交易所時間事件只是排序錨點，不代表因果、領先市場或預測；此模組不產生分數、A/A+、BUY/SELL 或 Shadow trade。reaction observation 以 `REACTION_CHAIN_V0_2` 寫入 SQLite observations。

這是可測試的工程骨架，不代表交易規則已完成市場實證。交易日曆、期交所商品規格、富邦 SDK 與每項門檻仍需用官方資料確認。

## 空明智慧資產內部標記

本專案之研究架構、資料模型、觀察流程、知識演化設計與實證資料，屬空明原創智慧資產。公開內容與核心實作應分層管理。不得公開真實 `.env`、登入或憑證資料、token、核心實證資料庫、未決定公開的研究規則，或完整私有 Prompt / Workflow。

## 環境

- 需求：Python 3.11+
- 本次檢查：Windows NT 10.0.26100 / PowerShell 5.1
- 使用者目前的 `PATH` 找不到 `python` 或 `py`
- Codex 隨附環境：Python 3.12.13（用於本次測試）
- 富邦 Neo 官方 SDK：尚未安裝或確認；專案不宣告未知套件名稱

## 安裝與執行

安裝 Python 3.11+ 後，在 PowerShell 執行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest
python -m kam_market_ai.app
```

安全入口只會初始化本機 Shadow SQLite 並顯示狀態，不會連接富邦或送單。

### 本機富邦授權 dry-run

先複製 `.env.example` 成為僅存在本機的 `.env`，在其中填入值；不要把內容貼到對話、日誌或 Git。預設只做設定完整性檢查，不登入、不讀取憑證、不建立行情連線：

```powershell
$env:PYTHONPATH = "src"
& "C:\Users\my092\AppData\Local\Programs\Python\Python312\python.exe" -m kam_market_ai.authorization.cli
```

只有本人在本機明確決定進行最小唯讀授權時，才使用 `--live`。該流程只建立已授權的 market-data clients，沒有訂閱、REST 請求或下單邏輯；授權層與 KAM engine／adapter 完全分離。

## 專案結構

```text
src/kam_market_ai/
├─ config.py                 # fail-closed 設定
├─ models.py                 # TAIEX/TX/MTX 統一模型
├─ session.py                # 日盤/夜盤 Session Engine
├─ candles.py                # 60K builder
├─ market_data/              # provider interface + 富邦安全 placeholder
├─ analysis/                 # 20MA、區間、環境、V 轉
├─ decision/                 # Hard Gate、分級、No Trade、Cause Health
├─ execution/                # Shadow-only 進出、停損、MFE/MAE
├─ risk/                     # 動態保證金與資金儀表板
├─ storage/                  # SQLite Shadow 實證資料
└─ logging_config.py         # 日誌與敏感內容遮罩
tests/                       # 安全與核心行為測試
docs/ARCHITECTURE.md         # 架構與邊界
docs/PHASE1_PLAN.md          # 第一階段計畫
```

## 富邦 Neo 後續整合前置條件

需要先取得並確認官方 SDK 的名稱、版本、支援的 Python 版本、行情登入/訂閱/歷史資料官方文件、商品代碼與授權範圍。完成確認後，只補 `FubonNeoMarketDataAdapter` 的唯讀行情行為；不得加入委託功能。不要把任何實際憑證交給本專案或寫入程式碼。

## 設計文件

- [架構與安全邊界](docs/ARCHITECTURE.md)
- [第一階段執行計畫](docs/PHASE1_PLAN.md)
