from test_replay_evaluator_adapter import Result
from kam_market_ai.replay.evaluator import FrozenEngineBundle
from kam_market_ai.replay.evaluator_adapter import FrozenEngineEvaluatorConfig, FrozenEngineReplayEvaluator
def test_engine_bundle_requires_explicit_version_matrix():
    bundle=FrozenEngineBundle(*(lambda value,timeframe:Result() for _ in range(4)),{})
    assert FrozenEngineReplayEvaluator(bundle,FrozenEngineEvaluatorConfig.provisional()).evaluator_version=="1.0"
