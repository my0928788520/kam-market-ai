from pathlib import Path


def test_v3_presentation_modules_do_not_import_engines_or_brokerage_dependencies():
    directory = Path(__file__).parents[1] / "src" / "kam_market_ai" / "dashboard"
    source = "\n".join(line for name in ("presenter.py", "wsgi_adapter.py", "ui_contract.py") for line in (directory / name).read_text(encoding="utf-8").splitlines() if line.startswith(("from ", "import "))).lower()
    forbidden = ("fubon", "broker", "execution", "decision_confidence", "risk_engine", "next_step_engine", "position_engine")
    assert all(token not in source for token in forbidden)
