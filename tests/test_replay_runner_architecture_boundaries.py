from pathlib import Path

def test_runner_modules_do_not_import_engines_dashboard_or_brokerage():
    directory=Path(__file__).parents[1]/"src"/"kam_market_ai"/"replay"
    imports="\n".join(line.lower() for path in directory.glob("*.py") for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(("from ","import ")))
    for token in ("kam_market_ai.decision", "kam_market_ai.dashboard", "fubon", "broker", "requests", "socket", "execution"): assert token not in imports
