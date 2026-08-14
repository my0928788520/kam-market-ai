# KAM 富邦五週期唯讀儀表板｜操作手冊

## 正式用途

這個入口只讀取 TMF 市場 K 線，產生 5 分、15 分、60 分、形成中日線與形成中週線的觀察結果。所有輸出固定為 `HOLD`／`BLOCKED`，沒有帳戶、委託或真實下單能力。

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
- 當天與本週資料不會被標示為完整日線／週線。
- Railway 只部署程式，不包含本機憑證或真實行情連線。
- `-PaperTestArmed` 只授權當次本機 Paper 工作階段；不改變
  `trading_enabled=false` 與 `live_order_allowed=false`。
