from test_replay_dashboard_read_model import _evaluated
from kam_market_ai.replay import ReplayPresenterConfig, ReplayPresenterSerializationConfig, build_replay_dashboard_read_model, build_replay_presenter, replay_presenter_to_canonical_json, serialize_replay_presenter
def test_replay_presenter_has_fixed_sections_and_safe_unavailable_values():
 view=build_replay_presenter(build_replay_dashboard_read_model(_evaluated(),total_frames=3),ReplayPresenterConfig())
 assert view.error_codes==()
 assert len(view.timeframe_cards)==4 and len(view.module_cards)==4 and view.header["product_name"]=="KAM Trade V3 Replay"
 assert replay_presenter_to_canonical_json(serialize_replay_presenter(view,ReplayPresenterSerializationConfig()),ReplayPresenterSerializationConfig())==replay_presenter_to_canonical_json(serialize_replay_presenter(view,ReplayPresenterSerializationConfig()),ReplayPresenterSerializationConfig())
