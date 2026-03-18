export function toFiniteNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

export function createLandingPreviewState(sharedConstants = {}) {
  const configuredTickers = Array.isArray(sharedConstants.backend?.tickers)
    ? sharedConstants.backend.tickers.map((ticker) => String(ticker))
    : [];
  const openingPrices = sharedConstants.backend?.opening_prices ?? {};
  const marketState = {};

  configuredTickers.forEach((ticker) => {
    marketState[ticker] = {
      ticker,
      price: toFiniteNumber(openingPrices[ticker]),
      bid: '--',
      ask: '--',
    };
  });

  return {
    tickers: configuredTickers,
    openingPrices,
    marketState,
  };
}

export function applyLandingSnapshot(
  marketState,
  ticker,
  snapshot = {},
  fallbackPrice = null,
) {
  const state = marketState[ticker] ?? {
    ticker,
    price: toFiniteNumber(fallbackPrice),
    bid: '--',
    ask: '--',
  };
  const bestBid = toFiniteNumber(snapshot.best_bid);
  const bestAsk = toFiniteNumber(snapshot.best_ask);
  const lastPrice = toFiniteNumber(snapshot.last_price);
  const resolvedFallbackPrice = toFiniteNumber(fallbackPrice);
  const displayPrice =
    bestBid !== null && bestAsk !== null && bestBid > 0 && bestAsk > 0
      ? (bestBid + bestAsk) / 2
      : lastPrice ?? resolvedFallbackPrice ?? state.price;

  marketState[ticker] = {
    ticker,
    price: displayPrice,
    bid: bestBid ?? state.bid,
    ask: bestAsk ?? state.ask,
  };

  return marketState[ticker];
}
