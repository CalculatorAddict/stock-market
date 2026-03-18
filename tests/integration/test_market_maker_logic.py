import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from websockets import ConnectionClosedOK
from websockets.frames import Close

from trading_bot.market_maker import MarketMaker


@pytest.fixture
def market_maker():
    return MarketMaker(client_user="test", auto_start=False)


@pytest.fixture
def mock_market_data():
    return {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5}


@pytest.fixture
def mock_empty_market():
    return {"best_bid": None, "best_ask": None, "last_price": 100.0}


def test_initialization(market_maker):
    assert market_maker.client_user == "test"
    assert market_maker.base_size == 50
    assert market_maker.min_quote_size == 1
    assert market_maker.max_quote_size == 5
    assert market_maker.volatility_window == 20
    assert market_maker.min_trade_interval == 0.5
    assert market_maker.max_trade_interval == 1.5
    assert market_maker.min_spread == 0.01
    assert market_maker.cancel_probability == 0.3
    assert market_maker.running is True


def test_initialization_can_skip_auto_start():
    with patch.object(MarketMaker, "run") as mock_run:
        market_maker = MarketMaker(client_user="test", auto_start=False)

    mock_run.assert_not_called()
    assert market_maker.client_user == "test"


def test_volatility_calculation(market_maker):
    assert market_maker.volatility("OGC") == 0.1

    market_maker.ticker_states["OGC"]["price_history"] = [100, 101, 99, 102, 100]
    volatility = market_maker.volatility("OGC")
    assert isinstance(volatility, float)
    assert volatility > 0


@pytest.mark.asyncio
async def test_process_market_update_initialization(market_maker, mock_empty_market):
    market_maker.ticker_states["OGC"]["inventory"] = 3
    market_maker.ticker_states["OGC"]["inventory_loaded"] = True
    mock_place_order = AsyncMock()
    market_maker.place_order = mock_place_order
    market_maker.quote_prices = MagicMock(return_value=(99.0, 101.0, 0.02, None, None))
    market_maker.quote_volume = MagicMock(side_effect=[2, 4])

    await market_maker.process_market_update("OGC", mock_empty_market)
    assert mock_place_order.call_count == 2

    calls = mock_place_order.call_args_list
    assert calls[0].args[0] == "OGC"
    assert calls[0].args[1] == "buy"
    assert calls[0].args[2] == 99.0
    assert calls[0].args[3] == 2

    assert calls[1].args[0] == "OGC"
    assert calls[1].args[1] == "sell"
    assert calls[1].args[2] == 101.0
    assert calls[1].args[3] == 3


@pytest.mark.asyncio
async def test_process_market_update_refreshes_quotes(market_maker, mock_market_data):
    market_data = {
        **mock_market_data,
        "all_bids": [
            {"order_id": "buy-1", "price": 149.0, "volume": 2},
        ],
        "all_asks": [
            {"order_id": "sell-1", "price": 152.0, "volume": 3},
        ],
    }
    market_maker.ticker_states["OGC"]["inventory"] = 5
    market_maker.ticker_states["OGC"]["inventory_loaded"] = True
    market_maker.ticker_states["OGC"]["next_order_time"] = datetime.now() - timedelta(
        seconds=1
    )

    async def _cancel_order(ticker, side, order_id):
        market_maker.ticker_states[ticker]["open_orders"][side].pop(order_id, None)
        return True

    mock_place_order = AsyncMock()
    market_maker.place_order = mock_place_order
    market_maker.cancel_order = AsyncMock(side_effect=_cancel_order)
    market_maker.quote_prices = MagicMock(return_value=(149.0, 152.0, 0.02, "up", None))
    market_maker.quote_volume = MagicMock(side_effect=[2, 3])
    market_maker.next_delay = MagicMock(return_value=1.0)
    market_maker.randomly_cancel_orders = AsyncMock()
    market_maker.ticker_states["OGC"]["open_orders"]["buy"]["buy-1"] = {
        "price": 149.0,
        "remaining_volume": 2,
    }
    market_maker.ticker_states["OGC"]["open_orders"]["sell"]["sell-1"] = {
        "price": 152.0,
        "remaining_volume": 3,
    }

    await market_maker.process_market_update("OGC", market_data)
    assert mock_place_order.called
    assert mock_place_order.call_count == 2
    assert market_maker.cancel_order.await_count == 2
    assert market_maker.cancel_order.await_args_list[0].args == ("OGC", "buy", "buy-1")
    assert market_maker.cancel_order.await_args_list[1].args == (
        "OGC",
        "sell",
        "sell-1",
    )


def test_quote_prices_can_cross_best_ask(market_maker):
    market_maker.bias_probability = 0
    market_maker.cross_probability = 1
    market_maker.spread_range = (0.02, 0.02)
    market_maker.quote_noise_range = (0.0, 0.0)

    with (
        patch("trading_bot.market_maker.random.uniform") as mock_uniform,
        patch("trading_bot.market_maker.random.random", side_effect=[0.5, 0.5]),
        patch("trading_bot.market_maker.random.choice", return_value="buy"),
    ):
        mock_uniform.side_effect = [0.02, 0.0, 0.002, 0.005]
        buy_price, sell_price, spread, bias, cross_side = market_maker.quote_prices(
            150.0, 151.0, 150.5
        )

    assert spread == 0.02
    assert bias is None
    assert cross_side == "buy"
    assert buy_price > 151.0
    assert sell_price > buy_price


@pytest.mark.asyncio
async def test_place_order(market_maker):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "order-1"
        mock_post.return_value = mock_response

        await market_maker.place_order("OGC", "buy", 150.0, 50)

    state = market_maker.ticker_states["OGC"]
    assert state["inventory"] == 0
    assert state["trades"] == []
    assert state["open_orders"]["buy"] == {
        "order-1": {"price": 150.0, "remaining_volume": 50}
    }


def test_reconcile_open_orders_records_fill(market_maker):
    state = market_maker.ticker_states["OGC"]
    state["inventory"] = 5
    state["inventory_loaded"] = True
    state["open_orders"]["sell"]["sell-1"] = {"price": 151.0, "remaining_volume": 3}

    market_maker.reconcile_open_orders(
        "OGC",
        {
            "all_bids": [],
            "all_asks": [],
        },
    )

    assert state["inventory"] == 2
    assert len(state["trades"]) == 1
    assert state["trades"][0]["side"] == "sell"
    assert state["trades"][0]["volume"] == 3
    assert state["open_orders"]["sell"] == {}


def test_load_inventory_uses_bot_config(market_maker):
    state = market_maker.ticker_states["OGC"]
    state["inventory"] = 0
    state["inventory_loaded"] = False
    market_maker.client_user = "bot_alpha"
    market_maker.bot_accounts = MarketMaker.load_bot_accounts()

    market_maker.load_inventory("OGC")

    assert state["inventory"] == 50
    assert state["inventory_loaded"] is True


def test_handle_shutdown(market_maker):
    market_maker.ticker_states["OGC"]["trades"] = [
        {
            "timestamp": datetime.now(),
            "side": "buy",
            "price": 150.0,
            "volume": 50,
            "pnl": -750,
        }
    ]
    market_maker.ticker_states["OGC"]["total_pnl"] = -750
    market_maker.ticker_states["OGC"]["inventory"] = 50

    with patch("sys.exit") as mock_exit:
        market_maker.handle_shutdown()
        mock_exit.assert_called_once_with(0)


def test_log_status(market_maker):
    market_maker.ticker_states["OGC"]["inventory"] = 50
    market_maker.ticker_states["OGC"]["total_pnl"] = -750
    market_maker.ticker_states["OGC"]["last_price"] = 150.0

    with patch("builtins.print") as mock_print:
        market_maker.log_status("OGC")
        assert mock_print.called


@pytest.mark.asyncio
async def test_listen_orderbook(market_maker):
    msg = '{"OGC": {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5}}'

    mock_ws = AsyncMock()
    mock_ws.__aenter__.return_value = mock_ws
    close = Close(1000, "done")
    mock_ws.recv.side_effect = [msg, ConnectionClosedOK(close, close, False)]

    mock_process_market_update = AsyncMock()
    market_maker.process_market_update = mock_process_market_update

    with patch("trading_bot.trading_bot.websockets.connect", return_value=mock_ws):
        await market_maker.listen_orderbook()

    mock_process_market_update.assert_called_once_with(
        "OGC",
        {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5},
    )
