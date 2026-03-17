import asyncio
from unittest.mock import MagicMock, patch

from TradingBot.TradingBot import TradingBot


def _build_bot(
    client_user: str = "test",
    api_url: str = "http://localhost:8000/api/place_order",
) -> TradingBot:
    with patch("TradingBot.TradingBot.TradingBot.listen_orderbook") as mock_listen:
        mock_listen.return_value = None
        return TradingBot(client_user=client_user, api_url=api_url)


def test_place_order_posts_to_configured_endpoint_with_expected_payload():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "buy", 150.0, 5))

    mock_post.assert_called_once_with(
        bot.api_url,
        json={
            "ticker": "AAPL",
            "side": "buy",
            "price": 150.0,
            "volume": 5,
            "client_user": bot.client_user,
        },
    )


def test_place_order_buy_updates_inventory_and_trade_log():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "buy", 150.0, 2))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 2
    assert state["total_pnl"] == -300.0
    assert len(state["trades"]) == 1
    assert state["trades"][0]["side"] == "buy"
    assert state["trades"][0]["price"] == 150.0
    assert state["trades"][0]["volume"] == 2


def test_place_order_sell_updates_inventory_and_trade_log():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "sell", 151.0, 3))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == -3
    assert state["total_pnl"] == 453.0
    assert len(state["trades"]) == 1
    assert state["trades"][0]["side"] == "sell"
    assert state["trades"][0]["price"] == 151.0
    assert state["trades"][0]["volume"] == 3


def test_place_order_does_not_update_state_on_http_failure():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "bad request"
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "buy", 200.0, 1))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 0
    assert state["total_pnl"] == 0
    assert state["trades"] == []


def test_place_order_can_execute_against_api_endpoint(api_client, monkeypatch):
    bot = _build_bot(
        client_user="tapple",
        api_url="http://local-test/api/place_order",
    )

    def _post_to_test_client(url, json):
        assert url == bot.api_url
        return api_client.post("/api/place_order", json=json)

    monkeypatch.setattr("TradingBot.TradingBot.requests.post", _post_to_test_client)

    asyncio.run(bot.place_order("AAPL", "buy", 110.0, 2))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 2
    assert len(state["trades"]) == 1

    orderbook_response = api_client.get("/api/get_all_bids", params={"ticker": "AAPL"})
    assert orderbook_response.status_code == 200
    assert any(
        order["price"] == 110.0 and order["volume"] == 2
        for order in orderbook_response.json()
    )
