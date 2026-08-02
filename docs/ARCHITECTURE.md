# V0.1 架構

資料流遵循「因 → 條件 → 行為 → 結果 → 修正」：

```text
富邦行情 adapter / 未來 replay provider
              ↓ 正規化 Tick / Candle
Session Engine → 60K Builder → Market Structure
                                   ↓
                     Hard Gate → WAIT / A / A+
                                   ↓（僅 ELIGIBLE）
                    Shadow Executor（MTX × 1）
                                   ↓
             Cause Health + Stop + MFE/MAE + 延遲
                                   ↓
                  SQLite + Log + Risk Dashboard
```

## 邊界與不變量

- `TRADING_ENABLED` 是程式常數 `False`；環境值若嘗試開啟，程式拒絕啟動。
- 專案不存在 broker order gateway、委託模型或真實下單方法。
- 富邦 adapter 只繼承市場行情介面；官方 SDK 未驗證前一律 `NotImplementedError`。
- 夜盤海外背景是明確的 availability gate，V0.1 不虛構資料。
- 保證金由 `MarginCatalog` 更新並附來源、生效時間，沒有預設固定金額。
- 歷史回放與即時行情共用 `MarketDataProvider` 與標準化模型。

## 模組責任

- `config`：安全設定、環境變數與 `.env`。
- `market_data`：行情 provider 抽象層與富邦 placeholder。
- `session` / `candles`：日夜盤分類與 60 分 K 聚合。
- `analysis`：20MA、動態區間、盤整/趨勢、V 轉原語。
- `decision`：Hard Gate、No Trade reasons、A/A+ 與原因健康度。
- `execution`：純記憶體 Shadow 交易、即時停損、MFE/MAE。
- `risk`：可更新保證金與資金風險快照。
- `storage` / `logging_config`：SQLite 實證紀錄與遮罩日誌。

## 富邦 Neo 唯讀行情邊界

富邦的授權登入層不在 KAM 專案邏輯中。本人於本機完成合法授權後，才可把四個已授權行情 client 注入 `AuthorizedMarketDataClients`：期貨 WebSocket/REST 與證券 WebSocket/REST。

`authorization` 是本機 bootstrap 邊界：它可在明確 live 模式下短暫建立 `FubonSDK`、執行登入與 `init_realtime()`，再只輸出四個行情 client。KAM engine、Shadow execution 與行情 adapter 均不取得 SDK、登入回傳的 account、帳密、憑證或 API Key。CLI 預設 dry-run，只檢查本機 `.env` 欄位是否齊全，且只輸出缺少欄位的數量。

登入成功閘門固定為：`login_result.is_success is True` 才能執行 `init_realtime()`。若失敗，授權層只回報固定泛用訊息，不讀取或輸出 SDK `message`、`data`、personal ID、密碼、憑證路徑或憑證密碼。`.env` 使用 `FUBON_NEO_PERSONAL_ID`，避免將 SDK 的 `personal_id` 誤填為期貨或證券帳號。

憑證密碼模式由非敏感 `FUBON_NEO_CERT_PASSWORD_MODE` 明確指定：`CUSTOM`（預設）要求憑證密碼並以四參數登入；`DEFAULT` 不要求或傳遞憑證密碼，改以三參數登入。每次 authorization 僅執行一次由模式決定的 login，絕不在失敗後 fallback 或 retry。

`FubonNeoMarketDataAdapter` 不 import `FubonSDK`、`CoreSDK`、`Order` 或 `FutOptOrder`，也不接收帳戶、帳密、身分資料、憑證或 API Key。它只把 futures `trades` 與 stock `indices/IR0001` 轉為 KAM `Tick`；`afterHours` 是保留的來源欄位，時段判讀仍由 `SessionEngine` 處理。

TX/MTX 的月份契約由 `VerifiedContractResolver` 注入；`FubonFuturesDiscovery` 僅保留 `futopt.intraday.tickers()` 查詢接口，絕不自行推測或硬寫月份。REST 歷史 K 線的參數與回應 decoder 必須由官方文件確認後注入；未設定時 adapter 拒絕呼叫而非猜測欄位。
