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
    return {"best_bid": 0, "best_ask": 0, "last_price": 100.0}


def test_initialization(bot):
    assert bot.client_user == "test"
    assert bot.base_size == 50
    assert bot.volatility_window == 20
    assert bot.min_trade_interval == 1
    assert bot.min_spread == 0.01
    assert bot.running is True


def test_volatility_calculation(bot):
    assert bot.volatility("AAPL") == 0.1

    bot.ticker_states["AAPL"]["price_history"] = [100, 101, 99, 102, 100]
    volatility = bot.volatility("AAPL")
    assert isinstance(volatility, float)
    assert volatility > 0


@pytest.mark.asyncio
async def test_market_make_initialization(bot, mock_empty_market):
    mock_place_order = AsyncMock()
    bot.place_order = mock_place_order

    await bot.market_make("AAPL", mock_empty_market)
    assert mock_place_order.call_count == 2

    calls = mock_place_order.call_args_list
    assert calls[0].args[0] == "AAPL"
    assert calls[0].args[1] == "buy"
    assert calls[0].args[3] == bot.base_size

    assert calls[1].args[0] == "AAPL"
    assert calls[1].args[1] == "sell"
    assert calls[1].args[3] == bot.base_size


@pytest.mark.asyncio
async def test_market_make_normal(bot, mock_market_data):
    bot.ticker_states["AAPL"]["inventory"] = 0
    bot.ticker_states["AAPL"]["last_trade_time"] = datetime.now() - timedelta(seconds=2)

    mock_place_order = AsyncMock()
    bot.place_order = mock_place_order

    await bot.market_make("AAPL", mock_market_data)
    assert mock_place_order.called
    assert mock_place_order.call_count == 2


@pytest.mark.asyncio
async def test_place_order(bot):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        await bot.place_order("AAPL", "buy", 150.0, 50)

    state = bot.ticker_states["AAPL"]
    assert state["inventory"] == 50
    assert len(state["trades"]) == 1
    assert state["trades"][0]["side"] == "buy"
    assert state["trades"][0]["price"] == 150.0
    assert state["trades"][0]["volume"] == 50


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
