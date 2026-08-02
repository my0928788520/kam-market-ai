"""Taiwan futures day/night session classification."""
from datetime import datetime, time, timedelta, timezone as fixed_timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .models import SessionKind

class SessionEngine:
    def __init__(self, timezone: str = "Asia/Taipei") -> None:
        try:
            self.tz: tzinfo = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            if timezone != "Asia/Taipei":
                raise
            # Windows Python may not bundle the IANA database. Taiwan has no DST.
            self.tz = fixed_timezone(timedelta(hours=8), name="Asia/Taipei")
    def classify(self, timestamp: datetime) -> SessionKind:
        local = timestamp.astimezone(self.tz) if timestamp.tzinfo else timestamp.replace(tzinfo=self.tz)
        t = local.time().replace(tzinfo=None)
        if local.weekday() < 5 and time(8, 45) <= t < time(13, 45): return SessionKind.DAY
        if local.weekday() < 5 and t >= time(15): return SessionKind.NIGHT
        if local.weekday() in {1,2,3,4,5} and t < time(5): return SessionKind.NIGHT
        return SessionKind.CLOSED
