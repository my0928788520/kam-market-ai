from pathlib import Path
def test_evaluation_adapter_has_no_brokerage_dashboard_wsgi_or_network_imports():
 source="\n".join((Path(__file__).parents[1]/"src"/"kam_market_ai"/"replay"/name).read_text(encoding="utf-8") for name in ("evaluator.py","evaluator_adapter.py","evaluation_contract.py")); assert all(token not in source.lower() for token in ("fubon","broker","dashboard","wsgi","requests","socket"))
