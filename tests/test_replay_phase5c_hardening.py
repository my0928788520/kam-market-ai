"""Release hardening evidence for the frozen, read-only Replay stack."""
from dataclasses import replace
from test_replay_dashboard_read_model import _evaluated
from kam_market_ai.replay import (ReplayApp,ReplayPresenterConfig,ReplayWSGIAdapterConfig,build_replay_dashboard_read_model,build_replay_presenter,build_replay_wsgi_context,compare_replay_frames,render_replay_ui)
def _presenter(): return build_replay_presenter(build_replay_dashboard_read_model(_evaluated(),total_frames=3),ReplayPresenterConfig())
def test_context_and_html_are_byte_deterministic_with_fixed_dom_contract():
 p=_presenter(); a=build_replay_wsgi_context(p,ReplayWSGIAdapterConfig()); b=build_replay_wsgi_context(p,ReplayWSGIAdapterConfig()); assert a==b and render_replay_ui(a)==render_replay_ui(b)
 html=render_replay_ui(a)
 for ident in ("replay-status-banner","replay-header","replay-hero","replay-progress","replay-decision","replay-comparison","replay-timeframes","replay-modules","replay-messages","replay-footer","replay-decision-direction","replay-decision-confidence","replay-decision-risk","replay-decision-next-step","replay-timeframe-15m","replay-timeframe-60m","replay-timeframe-1d","replay-timeframe-1w","replay-module-position","replay-module-trend","replay-module-structure","replay-module-timing"): assert f'id="{ident}"' in html
 assert html.count("<h1>")==1 and 'lang="zh-TW"' in html and "<script" not in html
def test_wsgi_http_policy_is_read_only_and_no_store():
 app=ReplayApp(_presenter()); seen=[]
 def start(status,headers): seen.extend((status,headers))
 assert b"Method Not Allowed" in b"".join(app({"REQUEST_METHOD":"POST","PATH_INFO":"/replay"},start)); assert seen[0].startswith("405")
 seen.clear(); body=b"".join(app({"REQUEST_METHOD":"GET","PATH_INFO":"/replay"},start)); assert seen[0].startswith("200") and ("Cache-Control","no-store") in seen[1] and b"KAM Trade V3 Replay" in body
def test_comparison_rejects_cross_scenario_without_mutating_frames():
 current=_evaluated(); changed=replace(current,frame=replace(current.frame,scenario_id="different")); result=compare_replay_frames(current,changed)
 assert "invalid_comparison_source" in result.error_codes and current.frame.scenario_id!="different"
