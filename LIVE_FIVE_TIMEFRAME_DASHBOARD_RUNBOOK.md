# KAM 富邦五週期唯讀儀表板｜操作手冊

## 正式用途

這個入口只讀取 TMF 市場 K 線，產生 5 分、15 分、60 分、形成中日線與形成中週線的觀察結果。所有輸出固定為 `HOLD`／`BLOCKED`，沒有帳戶、委託或真實下單能力。

## Windows 一鍵啟動

日盤：

```powershell
.\tools\start_fubon_five_timeframe_dashboard.ps1 -Symbol TMFH6
```

夜盤：

```powershell
.\tools\start_fubon_five_timeframe_dashboard.ps1 -Symbol TMFH6 -Session afterhours
```

啟動成功後會自動開啟：

- 儀表板：`http://127.0.0.1:8765/five-timeframe`
- 安全 JSON：`http://127.0.0.1:8765/api/five-timeframe`

服務預設每 60 秒更新一次。按 `Ctrl+C` 可安全停止。

## 安全邊界

- 只綁定本機 `127.0.0.1`，不對外公開。
- `.env` 與富邦登入資料只存在本機。
- 快照不保留 provider raw payload 或原始 K 棒。
- 當天與本週資料不會被標示為完整日線／週線。
- Railway 只部署程式，不包含本機憑證或真實行情連線。
