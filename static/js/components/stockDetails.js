// js/components/stockDetails.js

import { stockDataPrices } from '../data/stockData.js';       // historic price data
import { drawDetailedGraph } from './graph.js';              // to draw the stock chart
import { populateOrderBook } from './orderBook.js';          // to render order book
import { loggedIn } from '../main.js';                       // login flag
import { userData } from '../data/userData.js';              // current user info
import {
  getIdentityHeaderNames,
  getOrderbookSocketAddresses
} from '../config/sharedConstants.js';

async function fetchInitialPriceHistory(stockName, windowSeconds = 60) {
  const response = await fetch(
    `/prices?ticker=${encodeURIComponent(stockName)}&window=${windowSeconds}`
  );
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const payload = await response.json();
  return payload
    .map((point) => ({
      date: new Date(point.date),
      price: Number(point.price),
    }))
    .filter((point) => Number.isFinite(point.date.getTime()) && Number.isFinite(point.price));
}

// Opens a modal showing detailed info & order form for a given stock
export function openStockDetail(stockName) {
  // Create the modal container
  const modal = document.createElement('div');
  modal.classList.add('modal');
  modal.innerHTML = `
    <div class="modal-content">
      <span class="close-button">&times;</span>
      <h2>${stockName} Details</h2>
      <div class="modal-body">
        <!-- Graph -->
        <div class="graph-container"></div>

        <!-- Order Form -->
        <div class="order-form-section">
          <h3>Place Order</h3>
          <form id="order-form">
            <input type="number" id="order-amount" placeholder="Amount" required />

            <div class="order-type-toggle">
              <label>
                <input type="radio" name="order-type" value="market_buy" checked>
                Market Buy
              </label>
              <label>
                <input type="radio" name="order-type" value="market_sell">
                Market Sell
              </label>
              <label>
                <input type="radio" name="order-type" value="limit_buy">
                Limit Buy
              </label>
              <label>
                <input type="radio" name="order-type" value="limit_sell">
                Limit Sell
              </label>
            </div>

            <input
              type="number"
              id="order-limit-price"
              placeholder="Limit Price"
              style="display: none;"
              required
            />

            <button type="button" id="place-order-btn">Place Order</button>
          </form>
        </div>

        <!-- Order Book -->
        <button id="toggle-order-book-btn">Show Order Book</button>
        <div class="order-book-section" style="display: none;">
          <div id="order-book-${stockName}-container"></div>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  // Close handlers
  modal.querySelector('.close-button').addEventListener('click', () => {
    delete activeStockGraphs[stockName];
    document.body.removeChild(modal);
  });
  modal.addEventListener('click', e => {
    if (e.target === modal) {
      delete activeStockGraphs[stockName];
      document.body.removeChild(modal);
    }
  });

  // Draw the chart once modal is in DOM
  const graphContainer = modal.querySelector('.graph-container');
  void (async () => {
    let initialGraphData = stockDataPrices[stockName];
    try {
      const hydratedData = await fetchInitialPriceHistory(stockName);
      if (hydratedData.length) {
        stockDataPrices[stockName] = hydratedData;
        initialGraphData = hydratedData;
      }
    } catch (error) {
      console.error(`Failed to hydrate initial price history for ${stockName}:`, error);
    }

    if (!graphContainer.isConnected) {
      return;
    }

    const graph = drawDetailedGraph(
      graphContainer,
      initialGraphData,
      {
        height: 200,
        yKey: 'price',
        resizeOnWindow: false,
        margin: { left: 68 },
        initialTradeTimestamp: stockDataDynamic[stockName]?.last_timestamp ?? null,
      }
    );
    activeStockGraphs[stockName] = graph;

    if (stockDataDynamic[stockName]) {
      graph.update({
        price: stockDataDynamic[stockName].last_price,
        best_bid: stockDataDynamic[stockName].best_bid,
        best_ask: stockDataDynamic[stockName].best_ask,
        timestamp: stockDataDynamic[stockName].last_timestamp,
        server_time: stockDataDynamic[stockName].server_time,
      });
    }
  })();

  // Show/hide limit price input on order-type change
  const orderTypeInputs = modal.querySelectorAll('input[name="order-type"]');
  const limitPriceInput  = modal.querySelector('#order-limit-price');
  orderTypeInputs.forEach(input => {
    input.addEventListener('change', () => {
      limitPriceInput.style.display = input.value.startsWith('limit')
        ? 'block'
        : 'none';
    });
  });

  // Place order button
  modal.querySelector('#place-order-btn').addEventListener('click', () => {
    const selected = modal.querySelector('input[name="order-type"]:checked').value;
    handleOrder(stockName, selected, modal);
  });

  // Toggle order book section
  const toggleBtn        = modal.querySelector('#toggle-order-book-btn');
  const orderBookSection = modal.querySelector('.order-book-section');
  const bookContainer    = modal.querySelector(`#order-book-${stockName}-container`);

  toggleBtn.addEventListener('click', () => {
    const showing = orderBookSection.style.display === 'block';
    orderBookSection.style.display = showing ? 'none' : 'block';
    toggleBtn.textContent = showing ? 'Show Order Book' : 'Hide Order Book';

    if (!showing) {
      // populate with the latest dynamic data
      populateOrderBook(bookContainer, stockDataDynamic[stockName]);
    }
  });
}

// Handles sending the order to the backend API
async function handleOrder(stockName, orderType, modal) {
  if (!loggedIn) {
    alert("You must be signed in before placing any order!");
    return;
  }

  const username     = userData.username;
  const amountVal    = modal.querySelector('#order-amount').value.trim(); // volume of order
  const limitVal     = modal.querySelector('#order-limit-price').value.trim(); // price of limit order

  const isLimit = orderType.startsWith('limit');
  const isBuy = orderType.endsWith('_buy');
  const identityHeaderNames = await getIdentityHeaderNames();

  if (!amountVal || Number(amountVal) <= 0) {
    alert("Amount must be greater than 0!");
    return;
  }
  if (isLimit) {
    if (!limitVal || Number(limitVal) <= 0){
      alert("Please enter a valid limit price!");
      return;
    }

    const price = Number(limitVal);

    const tradeData = {
      ticker:      stockName,
      side:        isBuy ? 'buy' : 'sell',
      client_user: username,
      volume:      Number(amountVal),
      price:       price
    };

    console.log("Sending trade data:", tradeData);

    fetch('/api/place_order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email
      },
      body: JSON.stringify(tradeData)
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        console.log("Server Response:", data);
        alert("Order placed successfully!");
      })
      .catch(err => {
        console.error(err);
        alert("Failed to place the order. Please try again.");
      });
  } else { // market order

    const tradeData = {
      ticker:      stockName,
      side:        isBuy ? 'buy' : 'sell',
      client_user: username,
      volume:      Number(amountVal),
    };

    console.log("Sending trade data:", tradeData);

    fetch('/api/market_order', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email
      },
      body: JSON.stringify(tradeData)
    })
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        console.log("Server Response:", data);
        alert("Order placed successfully!");
      })
      .catch(err => {
        console.error(err);
        alert("Failed to place the order. Please try again.");
      });
  }
}

// WebSocket for live order book updates
let socket = null;
const stockDataDynamic = {};
const activeStockGraphs = {};

export function getLiveOrderbookSnapshots() {
  return stockDataDynamic;
}

function bindOrderbookSocketMessageHandler(activeSocket) {
  activeSocket.addEventListener("message", event => {
  const data = JSON.parse(event.data);
  const tickers = Object.keys(data || {});
  console.log("Data from OrderBook socket", data);
  tickers.forEach(ticker => {
    stockDataDynamic[ticker] = data[ticker];

    // Append to historic prices if timestamp is new
    const lastDate  = new Date(stockDataDynamic[ticker].last_timestamp);
    const history   = stockDataPrices[ticker];
    const lastEntry = history[history.length - 1];

    const nextPrice = Number(stockDataDynamic[ticker].last_price);
    if (
      Number.isFinite(lastDate.getTime()) &&
      Number.isFinite(nextPrice) &&
      Date.parse(lastEntry.date) != Date.parse(lastDate)
    ) {
      history.push({ date: lastDate, price: nextPrice });
    }

    const liveGraph = activeStockGraphs[ticker];
    if (liveGraph) {
      liveGraph.update({
        price: stockDataDynamic[ticker].last_price,
        best_bid: stockDataDynamic[ticker].best_bid,
        best_ask: stockDataDynamic[ticker].best_ask,
        timestamp: stockDataDynamic[ticker].last_timestamp,
        server_time: stockDataDynamic[ticker].server_time,
      });
    }

    // If order book is visible, refresh it
    const bookContainer = document.getElementById(`order-book-${ticker}-container`);
    if (bookContainer) {
      populateOrderBook(bookContainer, stockDataDynamic[ticker]);
    }
  });
  window.dispatchEvent(new CustomEvent('orderbook-updated'));
  });
}

async function connectOrderbookSocket() {
  const addresses = await getOrderbookSocketAddresses();
  const primarySocketAddress = addresses.primary;
  const fallbackSocketAddress = addresses.fallback;

  socket = new WebSocket(primarySocketAddress);
  bindOrderbookSocketMessageHandler(socket);

  socket.addEventListener("open", () => {
    console.log(`Connected to OrderBook WebSocket`);
  });

  socket.addEventListener("error", (error) => {
    console.error(`Failed to connect to ${primarySocketAddress}:`, error);
    console.log("Attempting to connect to fallback WebSocket address...");

    socket = new WebSocket(fallbackSocketAddress);
    bindOrderbookSocketMessageHandler(socket);

    socket.addEventListener("open", () => {
      console.log(`Connected to OrderBook WebSocket`);
    });
    socket.addEventListener("error", (fallbackError) => {
      console.error(`Failed to connect to ${fallbackSocketAddress}:`, fallbackError);
      console.log("Unable to connect to the WebSocket server. Please try again later.");
    });
    socket.addEventListener("close", () => {
      console.log("OrderBook WebSocket connection closed");
    });
  });

  socket.addEventListener("close", () => {
    console.log("OrderBook WebSocket connection closed");
  });
}

connectOrderbookSocket();
