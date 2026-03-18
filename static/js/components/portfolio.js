import { userData } from '../data/userData.js';
import { portfolioPerformanceData } from '../data/portfolioPerformance.js';
import { stockDataPrices } from '../data/stockData.js';
import { drawDetailedGraph } from './graph.js';
import { loggedIn } from '../main.js';
import { getIdentityHeaderNames } from '../config/sharedConstants.js';
import { getOwnedOrdersFromSnapshots, removeOwnedOrder } from './orderBook.js';
import { getLiveOrderbookSnapshots, openStockDetail } from './stockDetails.js';

let headerGraph;
let portfolioRenderVersion = 0;
let orderbookRefreshBound = false;
let livePortfolioIntervalId = null;
let portfolioHistoryIdentity = null;
let portfolioHistoryLoadingIdentity = null;
let portfolioHistoryRequestVersion = 0;
const hiddenOrderIds = new Set();
const PORTFOLIO_UPDATE_INTERVAL_MS = 1000;
const PORTFOLIO_HISTORY_WINDOW_SECONDS = 60;

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

function getLiveTickerPrice(ticker) {
  const snapshot = getLiveOrderbookSnapshots()[ticker];
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

  return null;
}

function getFallbackTickerPrice(ticker) {
  const history = stockDataPrices[ticker] || [];
  const lastPoint = history.length ? history[history.length - 1] : null;
  return toFiniteNumber(lastPoint?.price);
}

function getBestAvailablePortfolioValue() {
  let missingPricedHolding = false;
  const holdingsValue = userData.holdings.reduce((total, holding) => {
    const amount = toFiniteNumber(holding.amount) ?? 0;
    if (amount === 0) {
      return total;
    }

    const marketPrice =
      getLiveTickerPrice(holding.stock) ?? getFallbackTickerPrice(holding.stock);
    if (marketPrice === null) {
      missingPricedHolding = true;
      return total;
    }

    return total + amount * marketPrice;
  }, 0);

  if (missingPricedHolding) {
    const serverPortfolioValue = toFiniteNumber(userData.serverPortfolioValue);
    if (serverPortfolioValue !== null) {
      return serverPortfolioValue;
    }
  }

  return userData.balance + holdingsValue;
}

function recomputeLivePortfolioValue() {
  return getBestAvailablePortfolioValue();
}

function trimPortfolioPerformanceHistory(now) {
  const cutoff = now.getTime() - (PORTFOLIO_HISTORY_WINDOW_SECONDS * 1000);
  while (
    portfolioPerformanceData.length &&
    portfolioPerformanceData[0].date.getTime() < cutoff
  ) {
    portfolioPerformanceData.shift();
  }
}

function syncPortfolioPerformancePoint(currentValue, now = new Date()) {
  if (!Number.isFinite(currentValue)) {
    return;
  }

  const normalizedNow = now instanceof Date ? now : new Date(now);
  if (!Number.isFinite(normalizedNow.getTime())) {
    return;
  }

  trimPortfolioPerformanceHistory(normalizedNow);

  if (!portfolioPerformanceData.length) {
    portfolioPerformanceData.push({
      date: new Date(normalizedNow.getTime() - (PORTFOLIO_HISTORY_WINDOW_SECONDS * 1000)),
      value: currentValue,
    });
  }

  const lastEntry = portfolioPerformanceData[portfolioPerformanceData.length - 1];
  if (lastEntry && lastEntry.date.getTime() === normalizedNow.getTime()) {
    lastEntry.value = currentValue;
  } else {
    portfolioPerformanceData.push({ date: normalizedNow, value: currentValue });
  }

  trimPortfolioPerformanceHistory(normalizedNow);
}

function formatPortfolioPnlDisplay() {
  const currentValue = toFiniteNumber(userData.portfolioValue);
  if (currentValue === null) {
    return userData.pnl || 'N/A';
  }

  const historyBaseline = portfolioPerformanceData.find(
    (point) => Number.isFinite(point?.date?.getTime?.()) && Number.isFinite(point?.value)
  );
  const baselineValue = toFiniteNumber(historyBaseline?.value);
  if (baselineValue === null || baselineValue <= 0) {
    return userData.pnl || 'N/A';
  }

  const pnlPercent = ((currentValue - baselineValue) / baselineValue) * 100;
  const signPrefix = pnlPercent >= 0 ? '+' : '';
  return `${signPrefix}${pnlPercent.toFixed(2)}%`;
}

async function fetchPortfolioValueHistory(windowSeconds = PORTFOLIO_HISTORY_WINDOW_SECONDS) {
  const identityHeaderNames = await getIdentityHeaderNames();
  const response = await fetch(`/api/portfolio_values?window=${windowSeconds}`, {
    headers: {
      [identityHeaderNames.user]: userData.username,
      [identityHeaderNames.email]: userData.email,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const payload = await response.json();
  return payload
    .map((point) => ({
      date: new Date(point.date),
      value: Number(point.value),
    }))
    .filter((point) => Number.isFinite(point.date.getTime()) && Number.isFinite(point.value));
}

function applyTimedPortfolioMarketValue() {
  if (!loggedIn) {
    return;
  }

  const nextPortfolioValue = recomputeLivePortfolioValue();
  if (!Number.isFinite(nextPortfolioValue)) {
    return;
  }

  userData.portfolioValue = nextPortfolioValue;
  syncPortfolioPerformancePoint(nextPortfolioValue);
  updateHeader();

  if (headerGraph) {
    headerGraph.update({
      price: nextPortfolioValue,
      force_price: true,
    });
  }
}

async function hydratePortfolioHistory() {
  if (!loggedIn) {
    portfolioHistoryIdentity = null;
    portfolioHistoryLoadingIdentity = null;
    if (headerGraph?.replaceData) {
      headerGraph.replaceData([]);
    }
    return;
  }

  const currentIdentity = `${userData.username}|${userData.email}`;
  if (
    portfolioHistoryIdentity === currentIdentity ||
    portfolioHistoryLoadingIdentity === currentIdentity
  ) {
    return;
  }

  const requestVersion = ++portfolioHistoryRequestVersion;
  portfolioHistoryLoadingIdentity = currentIdentity;

  try {
    const history = await fetchPortfolioValueHistory();
    if (requestVersion !== portfolioHistoryRequestVersion) {
      return;
    }

    portfolioPerformanceData.splice(0, portfolioPerformanceData.length, ...history);
    if (history.length) {
      userData.portfolioValue = history[history.length - 1].value;
      trimPortfolioPerformanceHistory(new Date());
      updateHeader();
    }

    if (headerGraph?.replaceData) {
      headerGraph.replaceData(history);
    }
    portfolioHistoryIdentity = currentIdentity;
  } catch (error) {
    console.error('Failed to hydrate portfolio value history:', error);
  } finally {
    if (portfolioHistoryLoadingIdentity === currentIdentity) {
      portfolioHistoryLoadingIdentity = null;
    }
  }
}

export async function ensurePortfolioHistoryHydrated() {
  await hydratePortfolioHistory();
}

function startLivePortfolioInterval() {
  if (livePortfolioIntervalId !== null) {
    return;
  }

  livePortfolioIntervalId = window.setInterval(() => {
    applyTimedPortfolioMarketValue();
  }, PORTFOLIO_UPDATE_INTERVAL_MS);
}

function stopLivePortfolioInterval() {
  if (livePortfolioIntervalId === null) {
    return;
  }

  window.clearInterval(livePortfolioIntervalId);
  livePortfolioIntervalId = null;
  portfolioHistoryIdentity = null;
  portfolioHistoryLoadingIdentity = null;
}

function updateHeader() {
  const titleEl = document.getElementById('portfolio-title');
  titleEl.textContent = loggedIn
    ? `${userData.name}'s portfolio value:`
    : 'Your portfolio value:';

  const pnlValue = formatPortfolioPnlDisplay();
  userData.pnl = pnlValue;
  const isPositive = pnlValue.startsWith('+');
  document.getElementById('balance-header').textContent = `$${userData.portfolioValue.toFixed(2)}`;

  const pnlEl = document.getElementById('pnl-header');
  pnlEl.textContent = pnlValue;
  pnlEl.classList.remove('positive', 'negative');
  pnlEl.classList.add(isPositive ? 'positive' : 'negative');
}

function createSectionHeader(title) {
  const header = document.createElement('div');
  header.classList.add('portfolio-section-header');
  header.textContent = title;
  return header;
}

function createValueRow(label, value, onClick = null) {
  const row = document.createElement('div');
  row.classList.add('portfolio-row');

  if (onClick) {
    row.classList.add('portfolio-row--clickable');
    row.addEventListener('click', onClick);
  }

  const main = document.createElement('div');
  main.classList.add('portfolio-row-main');

  const labelEl = document.createElement('div');
  labelEl.classList.add('portfolio-row-label');
  labelEl.textContent = label;

  const valueEl = document.createElement('div');
  valueEl.classList.add('portfolio-row-value');
  valueEl.textContent = value;

  main.appendChild(labelEl);
  main.appendChild(valueEl);
  row.appendChild(main);

  return row;
}

function createInfoRow(text) {
  const row = document.createElement('div');
  row.classList.add('portfolio-row', 'portfolio-row--muted');

  const info = document.createElement('div');
  info.classList.add('portfolio-row-label');
  info.textContent = text;

  row.appendChild(info);
  return row;
}

function formatHoldingAmount(amount) {
  return `Amount: ${amount}`;
}

function formatOrderLabel(order) {
  return `${order.side} ${order.ticker} ${order.volume}@${Number(order.price).toFixed(2)}`;
}

function removeOrderFromSnapshots(orderId) {
  const snapshots = getLiveOrderbookSnapshots();
  Object.values(snapshots).forEach((snapshot) => {
    if (!snapshot) {
      return;
    }

    if (Array.isArray(snapshot.all_bids)) {
      snapshot.all_bids = snapshot.all_bids.filter((order) => order.order_id !== orderId);
    }
    if (Array.isArray(snapshot.all_asks)) {
      snapshot.all_asks = snapshot.all_asks.filter((order) => order.order_id !== orderId);
    }
  });
}

function updateOrderInSnapshots(orderId, nextPrice, nextVolume) {
  const snapshots = getLiveOrderbookSnapshots();
  Object.values(snapshots).forEach((snapshot) => {
    if (!snapshot) {
      return;
    }

    const matchingBid = Array.isArray(snapshot.all_bids)
      ? snapshot.all_bids.find((order) => order.order_id === orderId)
      : null;
    if (matchingBid) {
      matchingBid.price = nextPrice;
      matchingBid.volume = nextVolume;
    }

    const matchingAsk = Array.isArray(snapshot.all_asks)
      ? snapshot.all_asks.find((order) => order.order_id === orderId)
      : null;
    if (matchingAsk) {
      matchingAsk.price = nextPrice;
      matchingAsk.volume = nextVolume;
    }
  });
}

async function cancelPortfolioOrder(orderId, button) {
  const identityHeaderNames = await getIdentityHeaderNames();

  button.disabled = true;
  button.textContent = 'Cancelling...';

  try {
    const response = await fetch('/api/cancel_order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email,
      },
      body: JSON.stringify({ order_id: orderId }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    hiddenOrderIds.add(orderId);
    removeOwnedOrder(orderId);
    removeOrderFromSnapshots(orderId);
    refreshPortfolioList();
  } catch (error) {
    console.error('Failed to cancel portfolio order:', error);

    if (button.isConnected) {
      button.disabled = false;
      button.textContent = 'Cancel';
    }

    alert('Failed to cancel order.');
  }
}

async function submitPortfolioOrderEdit(order, nextPrice, nextQuantity, button) {
  const identityHeaderNames = await getIdentityHeaderNames();

  button.disabled = true;
  button.textContent = 'Saving...';

  try {
    const response = await fetch('/api/edit_order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email,
      },
      body: JSON.stringify({
        order_id: order.order_id,
        price: nextPrice,
        volume: nextQuantity,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    updateOrderInSnapshots(order.order_id, nextPrice, nextQuantity);
    refreshPortfolioList();
  } catch (error) {
    console.error('Failed to edit portfolio order:', error);

    if (button.isConnected) {
      button.disabled = false;
      button.textContent = 'Edit';
    }

    alert('Failed to edit order.');
  }
}

async function fetchPortfolioOrderStatus(orderId) {
  const identityHeaderNames = await getIdentityHeaderNames();
  const response = await fetch(
    `/api/order_status?order_id=${encodeURIComponent(orderId)}`,
    {
      headers: {
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email,
      },
    },
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

function openEditOrderModal(order, button) {
  const overlay = document.createElement('div');
  overlay.classList.add('portfolio-edit-modal');
  overlay.innerHTML = `
    <div class="portfolio-edit-dialog">
      <h3>Edit Order</h3>
      <div class="portfolio-edit-summary">${formatOrderLabel(order)}</div>
      <label class="portfolio-edit-field">
        <span>Price</span>
        <input type="number" step="0.01" value="${Number(order.price)}" />
      </label>
      <label class="portfolio-edit-field">
        <span>Quantity</span>
        <input type="number" step="1" value="${Number(order.volume)}" />
      </label>
      <div class="portfolio-edit-actions">
        <button type="button" class="portfolio-edit-btn portfolio-edit-btn--secondary">Close</button>
        <button type="button" class="portfolio-edit-btn">Save</button>
      </div>
    </div>
  `;

  const [priceInput, quantityInput] = overlay.querySelectorAll('input');
  const [closeButton, saveButton] = overlay.querySelectorAll('button');
  const summary = overlay.querySelector('.portfolio-edit-summary');

  const closeModal = () => {
    if (overlay.isConnected) {
      document.body.removeChild(overlay);
    }
  };

  closeButton.addEventListener('click', closeModal);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) {
      closeModal();
    }
  });

  saveButton.addEventListener('click', async () => {
    const nextPrice = Number(priceInput.value);
    const nextQuantity = Number(quantityInput.value);
    if (
      !Number.isFinite(nextPrice) ||
      !Number.isFinite(nextQuantity) ||
      nextPrice <= 0 ||
      nextQuantity <= 0
    ) {
      alert('Enter a valid price and quantity.');
      return;
    }

    saveButton.disabled = true;
    saveButton.textContent = 'Saving...';
    await submitPortfolioOrderEdit(order, nextPrice, nextQuantity, button);
    closeModal();
  });

  document.body.appendChild(overlay);
  void fetchPortfolioOrderStatus(order.order_id)
    .then((status) => {
      if (!summary.isConnected) {
        return;
      }

      const filledVolume = Number(status.executed_volume) || 0;
      const totalVolume = Number(status.total_volume) || Number(order.volume);
      summary.textContent = `${formatOrderLabel(order)} (${filledVolume}/${totalVolume})`;
    })
    .catch((error) => {
      console.error('Failed to load order status for edit modal:', error);
    });
  priceInput.focus();
  priceInput.select();
}

function createOrderRow(order) {
  const row = document.createElement('div');
  row.classList.add('portfolio-row');

  const main = document.createElement('div');
  main.classList.add('portfolio-row-main');

  const labelEl = document.createElement('div');
  labelEl.classList.add('portfolio-row-label');
  labelEl.textContent = formatOrderLabel(order);

  const actions = document.createElement('div');
  actions.classList.add('portfolio-row-actions');

  const editButton = document.createElement('button');
  editButton.type = 'button';
  editButton.classList.add('portfolio-row-btn');
  editButton.textContent = 'Edit';
  editButton.addEventListener('click', (event) => {
    event.stopPropagation();
    openEditOrderModal(order, editButton);
  });

  const cancelButton = document.createElement('button');
  cancelButton.type = 'button';
  cancelButton.classList.add('portfolio-row-btn');
  cancelButton.textContent = 'Cancel';
  cancelButton.addEventListener('click', (event) => {
    event.stopPropagation();
    void cancelPortfolioOrder(order.order_id, cancelButton);
  });

  actions.appendChild(editButton);
  actions.appendChild(cancelButton);
  main.appendChild(labelEl);
  row.appendChild(main);
  row.appendChild(actions);

  return row;
}

function renderStaticPortfolioRows(container, holdings) {
  container.innerHTML = '';
  container.appendChild(createSectionHeader('Cash'));
  container.appendChild(createValueRow('Cash', `$${userData.balance.toFixed(2)}`));

  container.appendChild(createSectionHeader('Stocks'));
  const nonZeroHoldings = holdings.filter((holding) => Number(holding.amount) !== 0);
  if (!nonZeroHoldings.length) {
    container.appendChild(createInfoRow('No stock holdings.'));
  } else {
    nonZeroHoldings.forEach((holding) => {
      container.appendChild(
        createValueRow(
          holding.stock,
          formatHoldingAmount(holding.amount),
          () => openStockDetail(holding.stock),
        ),
      );
    });
  }

  container.appendChild(createSectionHeader('Open Limit Orders'));
}

async function renderPortfolioList(container, holdings) {
  const renderVersion = ++portfolioRenderVersion;
  renderStaticPortfolioRows(container, holdings);

  const openOrdersAnchor = document.createElement('div');
  openOrdersAnchor.classList.add('portfolio-orders-anchor');
  container.appendChild(openOrdersAnchor);
  openOrdersAnchor.appendChild(createInfoRow('Loading open orders...'));

  const openOrders = await getOwnedOrdersFromSnapshots(getLiveOrderbookSnapshots());
  if (renderVersion !== portfolioRenderVersion || !openOrdersAnchor.isConnected) {
    return;
  }

  openOrdersAnchor.innerHTML = '';
  const visibleOrders = openOrders.filter((order) => !hiddenOrderIds.has(order.order_id));
  if (!visibleOrders.length) {
    openOrdersAnchor.appendChild(createInfoRow('No open limit orders.'));
    return;
  }

  visibleOrders.forEach((order) => {
    openOrdersAnchor.appendChild(createOrderRow(order));
  });
}

function refreshPortfolioList() {
  const portfolioList = document.getElementById('portfolio-list');
  if (!portfolioList) {
    return;
  }

  void renderPortfolioList(portfolioList, userData.holdings);
}

function bindOrderbookRefresh() {
  if (orderbookRefreshBound) {
    return;
  }

  orderbookRefreshBound = true;
  window.addEventListener('orderbook-updated', () => {
    refreshPortfolioList();
  });
}

export function initPortfolioView() {
  const graphDiv = document.getElementById('header-graph');
  headerGraph = drawDetailedGraph(graphDiv, loggedIn ? portfolioPerformanceData : [], {
    height: 200,
    yKey: 'value',
    xTickCount: 2,
    mobileXTickCount: 2,
    centerXAxisLabels: true,
    resizeOnWindow: true,
  });
  bindOrderbookRefresh();
  startLivePortfolioInterval();

  const portfolioList = document.getElementById('portfolio-list');
  const existingTitle = document.querySelector('.positions-title');
  if (!existingTitle && portfolioList?.parentNode) {
    const positionsTitle = document.createElement('h2');
    positionsTitle.textContent = 'Your Positions';
    positionsTitle.classList.add('positions-title');
    portfolioList.parentNode.insertBefore(positionsTitle, portfolioList);
  }

  refreshPortfolioList();
  updateHeader();
  void hydratePortfolioHistory();
}

export function populatePortfolio() {
  const portfolioList = document.getElementById('portfolio-list');
  const positionsTitle = document.querySelector('.positions-title');
  if (portfolioList?.parentNode && positionsTitle) {
    portfolioList.parentNode.insertBefore(positionsTitle, portfolioList);
  }

  refreshPortfolioList();
  if (!loggedIn) {
    updateHeader();
    stopLivePortfolioInterval();
    if (headerGraph?.replaceData) {
      headerGraph.replaceData([]);
    }
    return;
  }

  headerGraph?.resize?.();
  updateHeader();
  startLivePortfolioInterval();
  void hydratePortfolioHistory();
}
