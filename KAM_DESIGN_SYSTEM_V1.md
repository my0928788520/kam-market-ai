# KAM Design System V1.0

## Brand Identity

KAM 是深色模式、證據優先、三秒理解的市場覺察介面。所有 UI 使用共享
tokens，不得在個別頁面自行定義色彩；介面不承諾結果，也不得把模擬表現成
真實交易。

## Typography and Spacing

| Token | Use | Value |
| --- | --- | --- |
| `--kam-font-page-title` | Page Title | 26px |
| `--kam-font-card-title` | Card Title | 14px |
| `--kam-font-section` | Section | 12px |
| `--kam-font-body` | Body | 12px |
| `--kam-font-small` | Small | 11px |
| `--kam-font-number` | Large Number | 30px |

Radius, padding, grid gap, and desktop card heights are tokenized. Every card
has Header, Body, Footer; primary conclusions cannot be hidden by truncation.

## Card Library

Direction Card, Control Card, KAM Market Cycle Card, Timeframe Card, Health
Card, Position Card, Next Action Card, Proposal Card, Matching Card, Ledger
Card, and Footer Card are the only formal dashboard card families.

## Market Visualization

多空控制權固定為十格 glass/glow 膠囊比例，不是 progress bar；空方為紅／玫
紅，已確認多方為青綠。**KAM Market Cycle** 使用 inline SVG 與 curve-attached
glow marker，正式循環為低檔確認、起漲形成、多方延伸、高檔回落、起跌形成、
空方延伸、低點止跌。固定安全文字：

> 倒 U 為市場位置判讀，不是價格預測。

市場循環不得單獨觸發 order。

## Dashboard Layout

1440×900 與 1920×1080 均依固定順序：

`Header → Direction / Control / KAM Market Cycle → Timeframes → Health /
Position / Next Action → Proposal / Matching → Footer`.

桌面為 100vh、無主頁 scroll；grid child 固定 `min-width: 0`、`min-height: 0`，
只允許完整稽核細節局部捲動。

## Animation

允許短 hover、fade、glow、marker pulse、loading fade；禁止花俏或暗示確定性
的動畫。

## Component Contract and Rules

Proposal 統一 BUY／SELL／HOLD；Position 統一多單／空單／無部位；Status 統一
Blocked／Pending／Completed／Rejected（以 zh-TW 顯示）。正式 UI 禁止 JSON、
debug text、完整 hash；hash 僅顯示短碼與 tooltip。

## Product Principle

一頁看懂、三秒理解、唯一下一步、市場位置優先、風險優先。Rule 永遠先於
Proposal；Proposal 永遠先於 Matching；Matching 永遠先於真人交易。

## Adoption

所有 KAM Dashboard 先引用 `src/kam_market_ai/ui/design_tokens.css`，再依本文件
的 Card Library 與 Desktop Grid 實作及驗收。
