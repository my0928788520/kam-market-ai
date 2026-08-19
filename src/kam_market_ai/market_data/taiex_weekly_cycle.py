"""Official TWSE TAIEX weekly-cycle context for the local dashboard."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import urlopen


@dataclass(frozen=True, slots=True)
class TaiexWeeklyCycle:
    stage: str
    label: str
    last_close: Decimal | None
    ma20: Decimal | None
    week_end: date | None
    source: str = "TWSE_TAIEX_OFFICIAL_WEEKLY"

    def safe_payload(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "label": self.label,
            "last_close": str(self.last_close) if self.last_close is not None else None,
            "ma20": str(self.ma20) if self.ma20 is not None else None,
            "week_end": self.week_end.isoformat() if self.week_end else None,
            "source": self.source,
            "market": "台灣加權指數",
            "timeframe": "週線",
            "live_order_allowed": False,
        }


def classify_taiex_weekly_cycle(closes: tuple[tuple[date, Decimal], ...]) -> TaiexWeeklyCycle:
    if len(closes) < 21:
        return TaiexWeeklyCycle("U0", "週線資料不足", None, None, None)
    values = [value for _, value in closes]
    current, previous = values[-1], values[-2]
    ma20 = sum(values[-20:], Decimal(0)) / Decimal(20)
    previous_ma20 = sum(values[-21:-1], Decimal(0)) / Decimal(20)
    previous_above = previous >= previous_ma20
    above = current >= ma20
    distance = (current - ma20) / ma20
    ma_rising = ma20 > previous_ma20
    if above and not previous_above:
        stage, label = "U2", "起漲形成"
    elif not above and previous_above:
        stage, label = "U6", "起跌形成"
    elif above and ma_rising and distance >= Decimal("0.08"):
        stage, label = "U5", "高檔過熱"
    elif above and ma_rising:
        stage, label = ("U4", "多方延伸後段") if distance >= Decimal("0.04") else ("U3", "多方延伸初期")
    elif above:
        stage, label = "U4", "高檔回落"
    elif not ma_rising and current < previous:
        stage, label = "U7", "空方延伸"
    elif current >= previous:
        stage, label = "U8", "低檔止跌"
    else:
        stage, label = "U1", "低檔築底"
    return TaiexWeeklyCycle(stage, label, current, ma20, closes[-1][0])


class TaiexWeeklyCycleSource:
    def __init__(self, cache_path: str | Path, fetch_json: Callable[[str], object] | None = None) -> None:
        self.cache_path = Path(cache_path)
        self.fetch_json = fetch_json or self._fetch_json

    @staticmethod
    def _fetch_json(url: str) -> object:
        with urlopen(url, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _parse_date(value: str) -> date:
        year, month, day = (int(item) for item in value.split("/"))
        return date(year + 1911 if year < 1911 else year, month, day)

    def load(self, observed_at: datetime) -> TaiexWeeklyCycle:
        rows: dict[date, Decimal] = {}
        if self.cache_path.exists():
            cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
            rows = {date.fromisoformat(key): Decimal(value) for key, value in cached.items()}
        for offset in range(18):
            month_index = observed_at.year * 12 + observed_at.month - 1 - offset
            year, month0 = divmod(month_index, 12)
            url = (
                "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
                f"?date={year:04d}{month0 + 1:02d}01&response=json"
            )
            try:
                payload = self.fetch_json(url)
            except (OSError, TimeoutError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            for row in payload.get("data", ()):
                if isinstance(row, list) and len(row) >= 5:
                    rows[self._parse_date(str(row[0]))] = Decimal(str(row[4]).replace(",", ""))
        if rows:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps({item.isoformat(): str(value) for item, value in sorted(rows.items())}),
                encoding="utf-8",
            )
        weekly: dict[tuple[int, int], tuple[date, Decimal]] = {}
        for trading_day, close in sorted(rows.items()):
            iso = trading_day.isocalendar()
            weekly[(iso.year, iso.week)] = (trading_day, close)
        return classify_taiex_weekly_cycle(tuple(weekly.values()))


__all__ = ["TaiexWeeklyCycle", "TaiexWeeklyCycleSource", "classify_taiex_weekly_cycle"]
