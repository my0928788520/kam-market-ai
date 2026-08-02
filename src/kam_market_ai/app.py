"""Safe V0.1 status entry point. It never connects to a broker."""
from .config import Settings, TRADING_ENABLED
from .logging_config import configure_logging
from .storage import ShadowStore

def main() -> int:
    settings=Settings.load(); configure_logging(settings.log_level)
    ShadowStore(settings.database_path).initialize()
    print("空明期貨 KAM V0.1 — Shadow Mode")
    print(f"TRADING_ENABLED={TRADING_ENABLED}")
    print("今日無符合條件訊號，但隨時可能出現訊號。")
    return 0

if __name__ == "__main__": raise SystemExit(main())

