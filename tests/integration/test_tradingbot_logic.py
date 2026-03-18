import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from websockets import ConnectionClosedOK
from websockets.frames import Close

from TradingBot.TradingBot import TradingBot


@pytest.fixture
def bot():
    with patch("TradingBot.TradingBot.TradingBot.listen_orderbook") as mock_listen:
        mock_listen.return_value = None
        return TradingBot(client_user="test")


@pytest.fixture
def mock_market_data():
    return {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5}


@pytest.fixture
def mock_empty_market():
    return {"best_bid": None, "best_ask": None, "last_price": 100.0}


def test_initialization(bot):
    assert bot.client_user == "test"
    assert bot.base_size == 50
    assert bot.min_quote_size == 1
    assert bot.max_quote_size == 5
    assert bot.volatility_window == 20
    assert bot.min_trade_interval == 0.5
    assert bot.max_trade_interval == 1.5
    assert bot.min_spread == 0.01
    assert bot.cancel_probability == 0.3
    assert bot.running is True


def test_initialization_can_skip_auto_start():
    with patch.object(TradingBot, "run") as mock_run:
        bot = TradingBot(client_user="test", auto_start=False)

    mock_run.assert_not_called()
    assert bot.client_user == "test"


def test_volatility_calculation(bot):
    assert bot.volatility("AAPL") == 0.1

    bot.ticker_states["AAPL"]["price_history"] = [100, 101, 99, 102, 100]
    volatility = bot.volatility("AAPL")
    assert isinstance(volatility, float)
    assert volatility > 0


@pytest.mark.asyncio
async def test_market_make_initialization(bot, mock_empty_market):
    bot.ticker_states["AAPL"]["inventory"] = 3
    bot.ticker_states["AAPL"]["inventory_loaded"] = True
    mock_place_order = AsyncMock()
    bot.place_order = mock_place_order
    bot.quote_prices = MagicMock(return_value=(99.0, 101.0, 0.02, None, None))
    bot.quote_volume = MagicMock(side_effect=[2, 4])

    await bot.market_make("AAPL", mock_empty_market)
    assert mock_place_order.call_count == 2

    calls = mock_place_order.call_args_list
    assert calls[0].args[0] == "AAPL"
    assert calls[0].args[1] == "buy"
    assert calls[0].args[2] == 99.0
    assert calls[0].args[3] == 2

    assert calls[1].args[0] == "AAPL"
    assert calls[1].args[1] == "sell"
    assert calls[1].args[2] == 101.0
    assert calls[1].args[3] == 3


@pytest.mark.asyncio
async def test_market_make_normal(bot, mock_market_data):
    market_data = {
        **mock_market_data,
        "all_bids": [
            {"order_id": "buy-1", "price": 149.0, "volume": 2},
        ],
        "all_asks": [
            {"order_id": "sell-1", "price": 152.0, "volume": 3},
        ],
    }
    bot.ticker_states["AAPL"]["inventory"] = 5
    bot.ticker_states["AAPL"]["inventory_loaded"] = True
    bot.ticker_states["AAPL"]["next_order_time"] = datetime.now() - timedelta(seconds=1)

    async def _cancel_order(ticker, side, order_id):
        bot.ticker_states[ticker]["open_orders"][side].pop(order_id, None)
        return True

    mock_place_order = AsyncMock()
    bot.place_order = mock_place_order
    bot.cancel_order = AsyncMock(side_effect=_cancel_order)
    bot.quote_prices = MagicMock(return_value=(149.0, 152.0, 0.02, "up", None))
    bot.quote_volume = MagicMock(side_effect=[2, 3])
    bot.next_delay = MagicMock(return_value=1.0)
    bot.randomly_cancel_orders = AsyncMock()
    bot.ticker_states["AAPL"]["open_orders"]["buy"]["buy-1"] = {
        "price": 149.0,
        "remaining_volume": 2,
    }
    bot.ticker_states["AAPL"]["open_orders"]["sell"]["sell-1"] = {
        "price": 152.0,
        "remaining_volume": 3,
    }

    await bot.market_make("AAPL", market_data)
    assert mock_place_order.called
    assert mock_place_order.call_count == 2
    assert bot.cancel_order.await_count == 2
    assert bot.cancel_order.await_args_list[0].args == ("AAPL", "buy", "buy-1")
    assert bot.cancel_order.await_args_list[1].args == ("AAPL", "sell", "sell-1")


def test_quote_prices_can_cross_best_ask(bot):
    bot.bias_probability = 0
    bot.cross_probability = 1
    bot.spread_range = (0.02, 0.02)
    bot.quote_noise_range = (0.0, 0.0)

    with (
        patch("TradingBot.TradingBot.random.uniform") as mock_uniform,
        patch("TradingBot.TradingBot.random.random", side_effect=[0.5, 0.5]),
        patch("TradingBot.TradingBot.random.choice", return_value="buy"),
    ):
        mock_uniform.side_effect = [0.02, 0.0, 0.002, 0.005]
        buy_price, sell_price, spread, bias, cross_side = bot.quote_prices(
            150.0, 151.0, 150.5
        )

    assert spread == 0.02
    assert bias is None
    assert cross_side == "buy"
    assert buy_price > 151.0
    assert sell_price > buy_price


@pytest.mark.asyncio
async def test_place_order(bot):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "order-1"
        mock_post.return_value = mock_response

        await bot.place_order("AAPL", "buy", 150.0, 50)

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 0
    assert state["trades"] == []
    assert state["open_orders"]["buy"] == {
        "order-1": {"price": 150.0, "remaining_volume": 50}
    }


def test_reconcile_open_orders_records_fill(bot):
    state = bot.ticker_states["AAPL"]
    state["inventory"] = 5
    state["inventory_loaded"] = True
    state["open_orders"]["sell"]["sell-1"] = {"price": 151.0, "remaining_volume": 3}

    bot.reconcile_open_orders(
        "AAPL",
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


def test_load_inventory_uses_bot_config(bot):
    state = bot.ticker_states["AAPL"]
    state["inventory"] = 0
    state["inventory_loaded"] = False
    bot.client_user = "bot_alpha"
    bot.bot_accounts = TradingBot.load_bot_accounts()

    bot.load_inventory("AAPL")

    assert state["inventory"] == 50
    assert state["inventory_loaded"] is True


def test_handle_shutdown(bot):
    bot.ticker_states["AAPL"]["trades"] = [
        {
            "timestamp": datetime.now(),
            "side": "buy",
            "price": 150.0,
            "volume": 50,
            "pnl": -750,
        }
    ]
    bot.ticker_states["AAPL"]["total_pnl"] = -750
    bot.ticker_states["AAPL"]["inventory"] = 50

    with patch("sys.exit") as mock_exit:
        bot.handle_shutdown()
        mock_exit.assert_called_once_with(0)


def test_log_status(bot):
    bot.ticker_states["AAPL"]["inventory"] = 50
    bot.ticker_states["AAPL"]["total_pnl"] = -750
    bot.ticker_states["AAPL"]["last_price"] = 150.0

    with patch("builtins.print") as mock_print:
        bot.log_status("AAPL")
        assert mock_print.called


@pytest.mark.asyncio
async def test_listen_orderbook(bot):
    msg = '{"AAPL": {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5}}'

    mock_ws = AsyncMock()
    mock_ws.__aenter__.return_value = mock_ws
    close = Close(1000, "done")
    mock_ws.recv.side_effect = [msg, ConnectionClosedOK(close, close, False)]

    mock_market_make = AsyncMock()
    bot.market_make = mock_market_make

    with patch("websockets.connect", return_value=mock_ws):
        await bot.listen_orderbook()

    mock_market_make.assert_called_once_with(
        "AAPL",
        {"best_bid": 150.0, "best_ask": 151.0, "last_price": 150.5},
    )
