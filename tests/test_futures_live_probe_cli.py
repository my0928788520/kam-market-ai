import json

from kam_market_ai.market_data import futures_live_probe_cli


class NeverBootstrap:
    def run(self, *_: object, **__: object) -> object:
        raise AssertionError("live bootstrap must require --live")


def test_cli_requires_explicit_live_flag_before_authorization(capsys) -> None:
    assert futures_live_probe_cli.main([], bootstrap=NeverBootstrap()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"success": False, "failure_stage": "LIVE_FLAG_REQUIRED"}
