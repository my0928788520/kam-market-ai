# KAM 富邦五週期唯讀儀表板｜操作手冊

## 正式用途

這個入口以富邦唯讀即時 K 線搭配 TAIFEX 公開、已收盤歷史資料，產生
5 分、15 分、60 分、日線與週線的 KAM 觀察結果。市場方向仍是
`OBSERVATION_ONLY`；未啟用 Paper 測試時不建立任何模擬委託，也沒有真實帳戶、
券商委託或下單能力。

## Windows 一鍵啟動

日盤：

```powershell
.\tools\start_fubon_five_timeframe_dashboard.ps1
```

夜盤：

```powershell
.\tools\start_fubon_five_timeframe_dashboard.ps1 -Session afterhours
```

啟動成功後會自動開啟：

- 儀表板：`http://127.0.0.1:8765/five-timeframe`
- 安全 JSON：`http://127.0.0.1:8765/api/five-timeframe`

服務預設每 3 秒更新一次。按 `Ctrl+C` 可安全停止。
啟動器會用富邦官方商品清單與報價成交量解析唯一活動 TMF 契約；無資料或同量歧義時直接停止，不猜契約月份。需要重現特定契約時仍可加上 `-Symbol TMFH6`。

圖表的黃色水平線與「即時」數字，每 3 秒讀取一次富邦官方
`intraday.quote` 最後成交資料；沒有新成交時價格可以維持不變，但報價時間會
保留最後一筆成交時間。這條即時顯示路徑只供圖表觀看，不會進入 KAM 確認或
Paper 模擬撮合。KAM 與 Paper 邊界仍只使用已收盤、已驗證的 K 棒。

日線與週線圖在有效 TMF 即時報價存在時，會在 TAIFEX 官方已收盤
歷史後面加上一根虛線「本日形成中」或「本週形成中」K 棒。形成中
OHLC 來自同一 TMF 契約的盤中 15 分 K 與最後成交價；不會把大盤
現貨指數接到期貨 K 棒。夜盤形成中日線依「歸屬次一一般交易時段」
顯示下一交易日，週末會順延至週一。這兩根 K 棒永遠只存在圖表層，
不寫入官方歷史快取，也不會改變 KAM 或 Paper 的完整性門檻。

日盤首次啟動會從 TAIFEX 官方下載近 12 個交易日逐筆資料與約 420 日的
日行情，建立 `debug\five_timeframe\taifex_official_history.json` 雜湊快取；
通常需要 30 至 90 秒。終端出現 `INITIALIZING_OFFICIAL_HISTORY` 時請保持視窗
開啟。同一交易日後續啟動會先驗證快取雜湊，再直接使用快取。

官方歷史層只採用一般交易時段，並以每個交易日成交量最大的非價差 TMF
契約建立未回溯調整的連續序列。當日資料不認證為完整日線；本週資料不認證
為完整週線。夜盤歷史契約尚未核准，因此 `-Session afterhours` 仍會安全停在
`ATTESTATION_REQUIRED`。

## 選用：啟動 Paper 模擬買單紀錄

只有本人要進行模擬買單測試時，才加入一次性的人工授權開關：

```powershell
.\tools\start_fubon_five_timeframe_dashboard.ps1 -PaperTestArmed
```

啟用後仍不會連接券商下單端。系統只在 KAM 五週期自然形成
`LONG / PAPER_BUY` 時，以最新已驗證 5 分 K 收盤價建立一口 TMF 模擬買進，
並在本機 `debug\paper_trading\tmf_live_journal.json` 留下成交價、20 點停損、
40 點停利、未實現／已實現損益、MFE／MAE 與雜湊稽核紀錄。相同 5 分 K
每 3 秒重讀時不會重複下單。

## 安全邊界

- 只綁定本機 `127.0.0.1`，不對外公開。
- `.env` 與富邦登入資料只存在本機。
- 快照不保留 provider raw payload 或原始 K 棒。
- 本機 TAIFEX 快取只保存正規化 K 棒、來源日期與 SHA-256 雜湊，不保存下載原檔。
- 當天與本週資料不會被標示為完整日線／週線。
- Railway 只部署程式，不包含本機憑證或真實行情連線。
- `-PaperTestArmed` 只授權當次本機 Paper 工作階段；不改變
  `trading_enabled=false` 與 `live_order_allowed=false`。
