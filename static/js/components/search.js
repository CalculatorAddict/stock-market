// js/components/search.js
import { stockDataPrices }       from '../data/stockData.js';
import { getLiveOrderbookSnapshots, openStockDetail } from './stockDetails.js';

export function initSearchView() {
  const stocksGrid = document.querySelector('.stocks-grid');
  const searchInput = document.getElementById('stock-search-input');
  if (!stocksGrid || !searchInput) {
    return;
  }

  // Render initial full list
  renderStocks('');

  // When the user types, re-render matching stocks
  searchInput.addEventListener('input', () => {
    const query = searchInput.value.trim().toLowerCase();
    renderStocks(query);
  });

  window.addEventListener('orderbook-updated', () => {
    const query = searchInput.value.trim().toLowerCase();
    renderStocks(query);
  });

  function renderStocks(filter) {
    stocksGrid.innerHTML = '';

    // Get all stock names, filter by substring, case‑neutral
    const names = Object.keys(stockDataPrices)
      .filter(name => name.toLowerCase().includes(filter));

    if (names.length === 0) {
      stocksGrid.innerHTML = `<div class="no-results">No stocks match “${filter}”</div>`;
      return;
    }

    for (const stockName of names) {
      const latestPrice = getLatestDisplayPrice(stockName);

      const card = document.createElement('div');
      card.classList.add('stock-card');
      card.innerHTML = `
        <h3 class="stock-name">${stockName}</h3>
        <div class="stock-price">Price: $${latestPrice.toFixed(2)}</div>
      `;
      card.addEventListener('click', () => openStockDetail(stockName));
      stocksGrid.appendChild(card);
    }
  }
}

function getLatestDisplayPrice(stockName) {
  const snapshot = getLiveOrderbookSnapshots()[stockName];
  if (snapshot) {
    const bestBid = toFiniteNumber(snapshot.best_bid);
    const bestAsk = toFiniteNumber(snapshot.best_ask);
    if (bestBid !== null && bestAsk !== null && bestBid > 0 && bestAsk > 0) {
      return (bestBid + bestAsk) / 2;
    }

    const lastPrice = toFiniteNumber(snapshot.last_price);
    if (lastPrice !== null) {
      return lastPrice;
    }
  }

  const dataPoints = stockDataPrices[stockName] || [];
  const fallbackPrice = dataPoints.length
    ? toFiniteNumber(dataPoints[dataPoints.length - 1].price)
    : null;
  return fallbackPrice ?? 0;
}

function toFiniteNumber(value) {
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
