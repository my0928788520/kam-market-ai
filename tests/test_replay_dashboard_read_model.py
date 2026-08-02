from dataclasses import dataclass,replace
from test_replay_input_contract import events,metadata
from kam_market_ai.replay import (FrozenEngineBundle,FrozenEngineEvaluatorConfig,FrozenEngineReplayEvaluator,ReplayInputConfig,ReplayRunnerConfig,ReplayTimelineConfig,build_replay_scenario,build_replay_timeline,run_replay_timeline,evaluate_replay_frame,build_replay_dashboard_read_model,serialize_replay_dashboard_read_model,replay_dashboard_to_canonical_json)
@dataclass(frozen=True)
class Result: valid:bool=True; warnings:tuple=(); error_codes:tuple=()
def _evaluated():
 frame=run_replay_timeline(build_replay_timeline(build_replay_scenario(metadata(),events(),ReplayInputConfig.provisional()),ReplayTimelineConfig.provisional()),ReplayRunnerConfig.provisional()).frames[1]
 frame=replace(frame,timeframe_states={tf:replace(slot,input_snapshot={f"{x}_input":1 for x in ("position","trend","structure","timing")}) for tf,slot in frame.timeframe_states.items()})
 bundle=FrozenEngineBundle(*(lambda *_:Result() for _ in range(4)),{"position":"1.0","trend":"1.0","structure":"1.0","timing":"1.0"})
 return evaluate_replay_frame(frame,FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig()))
def test_initial_model_has_fixed_shape_and_deterministic_serialization():
 model=build_replay_dashboard_read_model(_evaluated(),total_frames=3)
 assert len(model.timeframe_cards)==4 and len(model.module_cards)==4 and model.messages==("initial_frame",)
 assert replay_dashboard_to_canonical_json(serialize_replay_dashboard_read_model(model))==replay_dashboard_to_canonical_json(serialize_replay_dashboard_read_model(model))
