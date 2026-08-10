# KAM Sprint 9A — 富邦期貨真實行情唯讀驗證

## 目的

Sprint 9A 只驗證富邦期貨行情授權、TX／MTX／TMF 契約辨識、即時成交資料、資料新鮮度、取消訂閱、斷線與受控重連。它不讀取帳戶、權益、保證金或持倉，也沒有委託、改單、刪單或平倉能力。

## 本機邊界

- 真實行情探針只允許在使用者 Windows 本機明確加上 `--live` 執行。
- `AuthorizationBootstrap` 登入後立即丟棄 login result，只向探針提供四個行情 client。
- 帳號、密碼、憑證路徑與憑證密碼只存在本機 `.env`，不輸出、不序列化、不進 Git。
- Railway 繼續使用 `offline-demo`；不得將本機 `.env` 複製到公開服務。
- `TRADING_ENABLED=False`、`account_connected=False`、`broker_connected=False`、`live_order_allowed=False`。

## 契約探索

探針依富邦官方 `intraday.tickers` 查詢 TAIFEX 指數期貨，再同時用商品前綴、月份字母、到期日與中文行情商品名稱驗證 TX、MTX、TMF 身分；其中 MTX 依行情簡稱「小型臺指」驗證，並同時接受完整名稱「小型臺指期貨」。候選契約使用 `intraday.quote` 的 `total.tradeVolume` 選擇唯一最高活動量契約；缺值或同量歧義一律停止，不猜月份。

## WebSocket 驗證

探針訂閱 `trades`，每個商品至少需收到一筆格式正確且在 freshness 門檻內的資料。取消訂閱使用 `subscribed` 事件回傳的 channel ID。指定 `--verify-reconnect` 時，第一次完整取消與斷線後，會以同一行情 client 再連線、重新驗證授權、重新訂閱、收取資料並清理一次。

## 輸出

CLI 只輸出安全 JSON：商品、provider symbol、標準契約月份、事件數、資料年齡、生命週期結果與安全旗標。原始 provider payload、成交價、帳戶資料與 SDK 錯誤文字不輸出。
