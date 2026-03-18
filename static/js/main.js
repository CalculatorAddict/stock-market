// js/main.js
import { userData } from './data/userData.js';
import { initPortfolioView } from './components/portfolio.js';
import { initSearchView } from './components/search.js';
import { populatePortfolio } from './components/portfolio.js';
import { ensurePortfolioHistoryHydrated } from './components/portfolio.js';
import { portfolioPerformanceData } from './data/portfolioPerformance.js';
import {
  getClientInfoSocketAddresses,
  getIdentityHeaderNames,
  getOrderbookSocketAddresses,
  getSharedConstants,
} from './config/sharedConstants.js';
import {
  applyLandingSnapshot,
  createLandingPreviewState,
  toFiniteNumber,
} from './landingPreview.mjs';

export var loggedIn = false;
let client_socket = null;
let landingMarketSocket = null;
let landingTickers = [];
const landingMarketState = {};
let landingPreviewInitPromise = null;

function formatPrice(value) {
  const numericValue = toFiniteNumber(value);
  return numericValue === null ? value : numericValue.toFixed(2);
}

function renderLandingPreview() {
  const rowsContainer = document.getElementById('landing-orderbook-rows');
  if (!rowsContainer) {
    return;
  }

  if (!landingTickers.length) {
    rowsContainer.innerHTML = `
      <div class="landing-orderbook-row">
        <span class="landing-orderbook-ticker">Local</span>
        <span class="landing-orderbook-price">Loading</span>
        <span class="landing-orderbook-bid">--</span>
        <span class="landing-orderbook-ask">--</span>
      </div>
    `;
    return;
  }

  rowsContainer.innerHTML = landingTickers
    .map((ticker) => landingMarketState[ticker])
    .map((row) => {
      const displayPrice = toFiniteNumber(row.price);
      return `
        <div class="landing-orderbook-row">
          <span class="landing-orderbook-ticker">${row.ticker}</span>
          <span class="landing-orderbook-price">${
            displayPrice === null ? '--' : displayPrice.toFixed(2)
          }</span>
          <span class="landing-orderbook-bid">${formatPrice(row.bid)}</span>
          <span class="landing-orderbook-ask">${formatPrice(row.ask)}</span>
        </div>
      `;
    })
    .join('');
}

async function initializeLandingPreviewState() {
  if (landingPreviewInitPromise) {
    await landingPreviewInitPromise;
    return;
  }

  landingPreviewInitPromise = (async () => {
    const sharedConstants = await getSharedConstants();
    const previewState = createLandingPreviewState(sharedConstants);
    landingTickers = previewState.tickers;
    Object.keys(landingMarketState).forEach((ticker) => {
      delete landingMarketState[ticker];
    });
    Object.assign(landingMarketState, previewState.marketState);
    renderLandingPreview();

    await Promise.all(
      landingTickers.map(async (ticker) => {
        try {
          const response = await fetch(
            `/api/get_best?ticker=${encodeURIComponent(ticker)}`,
          );
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const snapshot = await response.json();
          applyLandingSnapshot(
            landingMarketState,
            ticker,
            snapshot,
            previewState.openingPrices[ticker] ?? null,
          );
        } catch (error) {
          console.error(`Failed to hydrate landing market preview for ${ticker}:`, error);
        }
      }),
    );
  })();

  try {
    await landingPreviewInitPromise;
  } finally {
    renderLandingPreview();
  }
}

async function startLandingPreview() {
  await initializeLandingPreviewState();
  renderLandingPreview();
  if (landingMarketSocket !== null) {
    return;
  }

  void connectLandingMarketFeed();
}

function stopLandingPreview() {
  if (landingMarketSocket) {
    landingMarketSocket.close();
    landingMarketSocket = null;
  }
}

async function connectLandingMarketFeed() {
  const rowsContainer = document.getElementById('landing-orderbook-rows');
  if (!rowsContainer || loggedIn) {
    return;
  }

  const addresses = await getOrderbookSocketAddresses();
  const socket = new WebSocket(addresses.primary);
  landingMarketSocket = socket;

  const bindSocketEvents = (activeSocket) => {
    activeSocket.addEventListener('message', (event) => {
      const payload = JSON.parse(event.data);
      landingTickers.forEach((ticker) => {
        const snapshot = payload?.[ticker];
        if (!snapshot) {
          return;
        }

        applyLandingSnapshot(landingMarketState, ticker, snapshot);
      });
      renderLandingPreview();
    });

    activeSocket.addEventListener('close', () => {
      if (landingMarketSocket === activeSocket) {
        landingMarketSocket = null;
      }
    });

    activeSocket.addEventListener('error', (error) => {
      console.error('Landing market websocket failed:', error);
    });
  };

  bindSocketEvents(socket);
}

function initLandingAccordions() {
  const triggers = document.querySelectorAll('.landing-accordion-trigger');
  triggers.forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const panel = trigger.nextElementSibling;
      const expanded = trigger.getAttribute('aria-expanded') === 'true';
      trigger.setAttribute('aria-expanded', String(!expanded));
      panel.hidden = expanded;
    });
  });
}

function syncAuthShell() {
  const landing = document.getElementById('preauth-landing');
  const authenticatedPortfolio = document.getElementById('authenticated-portfolio');
  const portfolioNavButton = document.getElementById('nav-portfolio');

  if (landing) {
    landing.hidden = loggedIn;
  }
  if (authenticatedPortfolio) {
    authenticatedPortfolio.hidden = !loggedIn;
  }
  if (portfolioNavButton) {
    portfolioNavButton.setAttribute(
      'aria-label',
      loggedIn ? 'Portfolio' : 'Home',
    );
  }

  if (loggedIn) {
    stopLandingPreview();
  } else {
    void startLandingPreview();
  }
}

function applySignedOutState(loginSelect, loginBtn, signOutBtn) {
  if (client_socket) {
    client_socket.close();
    client_socket = null;
  }

  loggedIn = false;

  userData.name = 'Guest';
  userData.email = '';
  userData.clientInfoToken = '';
  userData.profilePicUrl = '';
  userData.first_name = 'Guest';
  userData.last_name = 'User';
  userData.username = '';
  userData.balance = 0;
  userData.serverPortfolioValue = null;
  userData.portfolioValue = 0;
  userData.pnl = 'N/A';
  userData.holdings = [];

  syncAuthShell();
  populatePortfolio();

  loginSelect.disabled = false;
  loginBtn.style.display = 'inline-block';
  signOutBtn.style.display = 'none';
}

async function loadDemoAccounts(loginSelect) {
  const fallbackAccounts = [
    { username: 'amorgan', email: 'alex.morgan@demo.local' },
    { username: 'jlee', email: 'jordan.lee@demo.local' },
  ];

  let accounts = fallbackAccounts;
  try {
    const response = await fetch('/api/demo');
    if (response.ok) {
      const body = await response.json();
      if (Array.isArray(body.accounts) && body.accounts.length > 0) {
        accounts = body.accounts;
      }
    }
  } catch (error) {
    console.warn('Could not load /api/demo, using fallback demo users.', error);
  }

  loginSelect.innerHTML = '';
  for (const account of accounts) {
    const option = document.createElement('option');
    option.value = account.email;
    option.dataset.username = account.username;
    option.textContent = `${account.username} (${account.email})`;
    loginSelect.appendChild(option);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  // Navigation + Views
  const navButtons = document.querySelectorAll('.nav-btn');
  const views = document.querySelectorAll('.view');
  let portfolioInitialized = false;
  let searchInitialized = false;

  // Default portfolio
  if (document.getElementById('portfolio-view').classList.contains('active')) {
    initPortfolioView();
    portfolioInitialized = true;
  }

  navButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      navButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      views.forEach((v) => v.classList.remove('active'));
      const target = btn.dataset.view;
      document.getElementById(target).classList.add('active');

      if (target === 'portfolio-view' && !portfolioInitialized) {
        initPortfolioView();
        portfolioInitialized = true;
      } else if (target === 'search-view' && !searchInitialized) {
        initSearchView();
        searchInitialized = true;
      }
    });
  });

  // Dark Mode
  const themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    document.body.classList.toggle('dark-mode', themeToggle.checked);
    themeToggle.addEventListener('change', () =>
      document.body.classList.toggle('dark-mode', themeToggle.checked),
    );
  }

  // Help Modal
  const helpBtn = document.getElementById('help-btn');
  const helpModal = document.getElementById('help-modal');
  const helpClose = document.getElementById('help-close');
  if (helpBtn && helpModal && helpClose) {
    helpBtn.addEventListener('click', () => (helpModal.style.display = 'flex'));
    helpClose.addEventListener('click', () => (helpModal.style.display = 'none'));
    helpModal.addEventListener('click', (e) => {
      if (e.target === helpModal) helpModal.style.display = 'none';
    });
  }

  // Static demo login
  const loginSelect = document.getElementById('static-login-user');
  const loginBtn = document.getElementById('static-login-btn');
  const signOutBtn = document.getElementById('static-signout-btn');
  const landingSignInBtn = document.getElementById('landing-signin-btn');

  await loadDemoAccounts(loginSelect);
  signOutBtn.style.display = 'none';
  initLandingAccordions();
  syncAuthShell();

  const handleSignIn = async () => {
    const selected = loginSelect.options[loginSelect.selectedIndex];
    if (!selected) {
      return;
    }

    loginBtn.disabled = true;
    try {
      const username = selected.dataset.username;
      const email = selected.value;

      userData.name = username;
      userData.first_name = username;
      userData.last_name = username;
      userData.email = email;

      // Wipe seeded values before live updates
      portfolioPerformanceData.splice(0, portfolioPerformanceData.length);

      await addClient({
        email,
        first_name: username,
        last_name: username,
      });

      loggedIn = true;
      syncAuthShell();
      loginSelect.disabled = true;
      loginBtn.style.display = 'none';
      signOutBtn.style.display = 'inline-block';
      await ensurePortfolioHistoryHydrated();
      connectClientSocket(userData.email);
      populatePortfolio();
    } catch (error) {
      console.error('Static login failed:', error);
      alert('Failed to sign in with demo account.');
    } finally {
      loginBtn.disabled = false;
    }
  };

  loginBtn.addEventListener('click', handleSignIn);
  landingSignInBtn?.addEventListener('click', () => {
    document.getElementById('nav-settings')?.click();
  });

  signOutBtn.addEventListener('click', () => {
    applySignedOutState(loginSelect, loginBtn, signOutBtn);
  });
});

// addClient function used when signing in
async function addClient(client_data) {
  const identityHeaderNames = await getIdentityHeaderNames();

  const response = await fetch('/api/add_new_client', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      [identityHeaderNames.email]: userData.email,
    },
    body: JSON.stringify(client_data),
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  console.log('Server Response Client Object:', data);
  userData.username = data.username;
  return data;
}

async function fetchClientInfoToken(email) {
  const identityHeaderNames = await getIdentityHeaderNames();
  const response = await fetch(
    `/api/client_info_token?email=${encodeURIComponent(email)}`,
    {
      headers: {
        [identityHeaderNames.user]: userData.username,
        [identityHeaderNames.email]: userData.email,
      },
    },
  );

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const payload = await response.json();
  userData.clientInfoToken = payload.token;
  return payload.token;
}

// WebSocket used to update client data and the portfolio view
async function connectClientSocket(email) {
  // Close the existing WebSocket connection if it exists
  if (client_socket) {
    console.log('Closing existing WebSocket connection...');
    client_socket.close();
  }

  // Define primary and fallback WebSocket addresses
  const addresses = await getClientInfoSocketAddresses();
  const primaryAddress = addresses.primary;
  const token = await fetchClientInfoToken(email);

  // Create a new WebSocket connection
  client_socket = new WebSocket(primaryAddress);

  // Handle connection open
  client_socket.addEventListener('open', () => {
    console.log(`Connected to Client Info for client with email: ${email}`);
    client_socket.send(
      JSON.stringify({
        email,
        token,
      }),
    );
  });

  // Handle errors
  client_socket.addEventListener('error', (error) => {
    console.error(`Failed to connect to ${primaryAddress}:`, error);
    alert('Unable to connect to the local WebSocket server. Please verify the app is running.');
  });

  // Handle incoming messages
  client_socket.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    console.log(`Client ${email} update:`, data);

    // Update userData with balance
    userData.balance = data.balance;

    // Keep the backend value as a fallback, but do not overwrite the
    // live mid-price portfolio value on every client-info tick.
    userData.serverPortfolioValue = data.portfolioValue;
    if (!Number.isFinite(userData.portfolioValue) || userData.portfolioValue <= 0) {
      userData.portfolioValue = data.portfolioValue;
    }

    // Update userData with pnl value
    userData.pnl = data.portfolioPnl.toFixed(2).concat('%');
    if (data.portfolioPnl >= 0) userData.pnl = '+'.concat(userData.pnl);

    // Update portfolio performance with portfolio pnl value and current timestamp
    const currentDate = new Date(Date.now());
    let needAdd = true;

    if (portfolioPerformanceData.length) {
      const lastEntry =
        portfolioPerformanceData[portfolioPerformanceData.length - 1];
      const diffMinutes = (currentDate - lastEntry.date) / 60000;
      needAdd =
        lastEntry.value !== userData.portfolioValue && diffMinutes >= 5;
    }

    if (needAdd) {
      portfolioPerformanceData.push({ date: currentDate, value: userData.portfolioValue });
      console.log('new portfolio data', {
        date: currentDate,
        value: userData.portfolioValue,
      });
      console.log(portfolioPerformanceData);
    }

    userData.holdings = [];
    for (const [key, value] of Object.entries(data.portfolio)) {
      const newHolding = {
        stock: key,
        amount: value,
        pnl: data.pnlInfo[key].toFixed(2).concat('%'),
      };

      userData.holdings.push(newHolding);
    }

    console.log('userData info', userData);

    // Update the portfolio view
    populatePortfolio();
  });

  // Handle connection close
  client_socket.addEventListener('close', () => {
    console.log('Client Info WebSocket connection closed');
  });

  // Handle errors
  client_socket.addEventListener('error', (error) => {
    console.error('Client Info WebSocket error:', error);
  });
}
