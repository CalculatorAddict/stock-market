import asyncio
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from TradingBot.TradingBot import TradingBot


def _build_bot(
    client_user: str = "test",
    client_email: str | None = None,
    api_url: str = "http://localhost:8000/api/place_order",
    include_email_header: bool = False,
) -> TradingBot:
    with patch("TradingBot.TradingBot.TradingBot.listen_orderbook") as mock_listen:
        mock_listen.return_value = None
        return TradingBot(
            client_user=client_user,
            client_email=client_email,
            api_url=api_url,
            include_email_header=include_email_header,
        )


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
        headers={
            "X-Actor-User": bot.client_user,
        },
    )


def test_place_order_includes_email_header_when_configured():
    bot = _build_bot(
        client_user="bot_beta",
        client_email="bot.beta@demo.local",
        include_email_header=True,
    )

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
        headers={
            "X-Actor-User": bot.client_user,
            "X-Actor-Email": bot.client_email,
        },
    )


def test_place_order_buy_tracks_open_order_without_mutating_inventory():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "buy-order-id"
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "buy", 150.0, 2))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 0
    assert state["total_pnl"] == 0
    assert state["trades"] == []
    assert state["open_orders"]["buy"] == {
        "buy-order-id": {"price": 150.0, "remaining_volume": 2}
    }


def test_place_order_sell_tracks_open_order_without_going_negative():
    bot = _build_bot()

    with patch("TradingBot.TradingBot.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "sell-order-id"
        mock_post.return_value = mock_response

        asyncio.run(bot.place_order("AAPL", "sell", 151.0, 3))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 0
    assert state["total_pnl"] == 0
    assert state["trades"] == []
    assert state["open_orders"]["sell"] == {
        "sell-order-id": {"price": 151.0, "remaining_volume": 3}
    }


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
        client_user="bot_alpha",
        client_email="bot.alpha@demo.local",
        api_url="http://local-test/api/place_order",
        include_email_header=True,
    )

    def _post_to_test_client(url, json, headers=None):
        assert url == bot.api_url
        return api_client.post("/api/place_order", json=json, headers=headers)

    monkeypatch.setattr("TradingBot.TradingBot.requests.post", _post_to_test_client)

    asyncio.run(bot.place_order("AAPL", "buy", 110.0, 2))

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 0
    assert state["trades"] == []
    assert len(state["open_orders"]["buy"]) == 1

    orderbook_response = api_client.get("/api/get_all_bids", params={"ticker": "AAPL"})
    assert orderbook_response.status_code == 200
    assert any(
        order["price"] == 110.0 and order["volume"] == 2
        for order in orderbook_response.json()
    )


def test_api_rejects_place_order_without_actor_headers(app_module):
    with TestClient(app_module.app) as client:
        response = client.post(
            "/api/place_order",
            json={
                "ticker": "AAPL",
                "side": "buy",
                "price": 110.0,
                "volume": 1,
                "client_user": "amorgan",
            },
        )

    assert response.status_code == 401
    assert "Missing identity headers" in response.json()["detail"]
