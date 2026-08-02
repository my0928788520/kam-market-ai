from test_replay_input_contract import events, metadata
from kam_market_ai.replay import ReplayEvaluationState, ReplayFrameState, ReplayInputConfig, ReplayRunnerConfig, ReplayTimelineConfig, build_replay_scenario, build_replay_timeline, run_replay_timeline

def test_input_only_runner_emits_deterministic_boundary_frames():
    timeline = build_replay_timeline(build_replay_scenario(metadata(), events(), ReplayInputConfig.provisional()), ReplayTimelineConfig.provisional())
    run = run_replay_timeline(timeline, ReplayRunnerConfig.provisional())
    assert run.valid and run.completion_state == "completed" and run.emitted_frame_count == 3
    assert run.frames[0].frame_state is ReplayFrameState.SCENARIO_STARTED
    assert run.frames[-1].frame_state is ReplayFrameState.SCENARIO_COMPLETED
    assert all(frame.evaluation_state is ReplayEvaluationState.NOT_EVALUATED for frame in run.frames)
