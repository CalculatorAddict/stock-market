"""Helpers for launching multiple demo trading bots at once."""

import argparse
import asyncio

from trading_bot.market_maker import MarketMaker


BOT_PROFILES = [
    {
        "client_user": "bot_alpha",
        "client_email": "bot.alpha@demo.local",
        "min_quote_size": 1,
        "max_quote_size": 4,
        "min_trade_interval": 0.35,
        "max_trade_interval": 0.9,
        "spread_range": (0.008, 0.02),
        "bias_probability": 0.25,
        "cross_probability": 0.18,
        "cancel_probability": 0.35,
    },
    {
        "client_user": "bot_beta",
        "client_email": "bot.beta@demo.local",
        "min_quote_size": 2,
        "max_quote_size": 5,
        "min_trade_interval": 0.4,
        "max_trade_interval": 1.0,
        "spread_range": (0.012, 0.028),
        "bias_probability": 0.2,
        "cross_probability": 0.14,
        "cancel_probability": 0.3,
    },
]


async def run_bots(bot_count):
    """Start the requested number of demo bots and await all websocket loops."""
    selected_profiles = BOT_PROFILES[:bot_count]
    bots = [MarketMaker(auto_start=False, **profile) for profile in selected_profiles]
    await asyncio.gather(*(bot.listen_orderbook() for bot in bots))


def main():
    """Parse CLI flags and launch a bounded number of demo bot profiles."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-count", type=int, default=2)
    args = parser.parse_args()

    bot_count = max(1, min(args.bot_count, len(BOT_PROFILES)))
    asyncio.run(run_bots(bot_count))


if __name__ == "__main__":
    main()
