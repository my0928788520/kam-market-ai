"""Fail-closed application configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

TRADING_ENABLED: bool = False
RESEARCH_MODE: bool = True

class UnsafeConfigurationError(RuntimeError):
    pass

def load_dotenv_values(path: str | Path) -> dict[str, str]:
    """Read local .env values without interpolation or logging."""
    path = Path(path)
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum():
            values[key] = value.strip().strip("'\"")
    return values

@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    timezone: str = "Asia/Taipei"
    database_path: Path = Path("data/kam_shadow.db")
    log_level: str = "INFO"
    trading_enabled: bool = False

    def __post_init__(self) -> None:
        if self.trading_enabled is not False or TRADING_ENABLED is not False:
            raise UnsafeConfigurationError("Real trading is permanently disabled in KAM V0.1")

    @classmethod
    def load(cls, env_path: str | Path = ".env") -> "Settings":
        file_values = load_dotenv_values(env_path)
        get = lambda key, default: os.environ.get(key, file_values.get(key, default))
        if get("TRADING_ENABLED", "False").strip().lower() not in {"false", "0", "no", "off"}:
            raise UnsafeConfigurationError("TRADING_ENABLED must remain False; refusing to start")
        return cls(get("KAM_ENV", "development"), get("KAM_TIMEZONE", "Asia/Taipei"),
                   Path(get("KAM_DATABASE_PATH", "data/kam_shadow.db")),
                   get("KAM_LOG_LEVEL", "INFO").upper(), False)
