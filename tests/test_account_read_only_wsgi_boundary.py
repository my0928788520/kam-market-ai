from kam_market_ai import account_read_only


def test_account_read_only_source_has_no_order_client_or_network_dependency() -> None:
    source = open(account_read_only.__file__, encoding="utf-8").read()
    for forbidden in ("requests", "urllib", "socket", "websocket", "fubon", "order_client", "place_order"):
        assert forbidden not in source
