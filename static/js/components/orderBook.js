import { userData } from '../data/userData.js';
import { getIdentityHeaderNames } from '../config/sharedConstants.js';

let ownershipActorKey = '';
const ownedOrderIds = new Set();
let ownedOrderIdsLoaded = false;
let pendingOwnedOrderRefresh = null;

function resetOwnershipCacheIfActorChanged() {
  const nextActorKey = `${userData.username || ''}|${userData.email || ''}`;
  if (nextActorKey === ownershipActorKey) {
    return;
  }

  ownershipActorKey = nextActorKey;
  ownedOrderIds.clear();
  ownedOrderIdsLoaded = false;
  pendingOwnedOrderRefresh = null;
}

export function invalidateOwnedOrderCache() {
  ownedOrderIds.clear();
  ownedOrderIdsLoaded = false;
  pendingOwnedOrderRefresh = null;
}

export function markOwnedOrder(orderId) {
  if (typeof orderId !== 'string' || !orderId) {
    return;
  }

  resetOwnershipCacheIfActorChanged();
  ownedOrderIds.add(orderId);
}

export function removeOwnedOrder(orderId) {
  if (typeof orderId !== 'string' || !orderId) {
    return;
  }

  ownedOrderIds.delete(orderId);
}

async function ensureOwnedOrderIdsLoaded() {
  resetOwnershipCacheIfActorChanged();

  if (!userData.username || !userData.email) {
    return false;
  }

  if (ownedOrderIdsLoaded) {
    return true;
  }

  if (!pendingOwnedOrderRefresh) {
    pendingOwnedOrderRefresh =
      (async () => {
        try {
          const identityHeaderNames = await getIdentityHeaderNames();
          const response = await fetch('/api/open_orders', {
            headers: {
              [identityHeaderNames.user]: userData.username,
              [identityHeaderNames.email]: userData.email,
            },
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }

          const orderIds = await response.json();
          ownedOrderIds.clear();
          if (Array.isArray(orderIds)) {
            orderIds.forEach((ownedOrderId) => {
              if (typeof ownedOrderId === 'string' && ownedOrderId) {
                ownedOrderIds.add(ownedOrderId);
              }
            });
          }

          ownedOrderIdsLoaded = true;
          return true;
        } catch (error) {
          console.error('Failed to load owned orders:', error);
          return false;
        } finally {
          pendingOwnedOrderRefresh = null;
        }
      })();
  }

  return pendingOwnedOrderRefresh;
}

async function isOwnOrder(orderId) {
  if (!(await ensureOwnedOrderIdsLoaded())) {
    return false;
  }

  return ownedOrderIds.has(orderId);
}

async function cancelOrderFromBook(orderId, button) {
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

    removeOwnedOrder(orderId);

    if (button.isConnected) {
      button.textContent = 'Canceled';
    }
  } catch (error) {
    console.error('Failed to cancel order from book:', error);

    if (button.isConnected) {
      button.disabled = false;
      button.textContent = 'Cancel';
    }

    alert('Failed to cancel order.');
  }
}

function buildOrderRow(order) {
  const row = document.createElement('tr');

  const priceCell = document.createElement('td');
  priceCell.textContent = order.price;

  const volumeCell = document.createElement('td');
  const levelContent = document.createElement('div');
  levelContent.classList.add('order-book-level');

  const volumeText = document.createElement('span');
  volumeText.textContent = order.volume;
  levelContent.appendChild(volumeText);
  volumeCell.appendChild(levelContent);

  row.appendChild(priceCell);
  row.appendChild(volumeCell);

  void (async () => {
    if (!(await isOwnOrder(order.order_id))) {
      return;
    }

    if (!levelContent.isConnected) {
      return;
    }

    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.classList.add('order-book-cancel-btn');
    cancelButton.textContent = 'Cancel';
    cancelButton.addEventListener('click', (event) => {
      event.stopPropagation();
      void cancelOrderFromBook(order.order_id, cancelButton);
    });
    levelContent.appendChild(cancelButton);
  })();

  return row;
}

function buildSideSection(title, orders) {
  const section = document.createElement('div');
  section.classList.add(title === 'Bids' ? 'order-book-bids' : 'order-book-asks');
  section.innerHTML = `
    <h4>${title}</h4>
    <table>
      <thead>
        <tr><th>Price</th><th>Volume</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  `;

  const tbody = section.querySelector('tbody');
  orders.forEach((order) => {
    tbody.appendChild(buildOrderRow(order));
  });

  return section;
}

export async function getOwnedOrdersFromSnapshots(snapshotMap) {
  resetOwnershipCacheIfActorChanged();

  const lookups = [];
  for (const [ticker, snapshot] of Object.entries(snapshotMap || {})) {
    const bids = Array.isArray(snapshot?.all_bids) ? snapshot.all_bids : [];
    const asks = Array.isArray(snapshot?.all_asks) ? snapshot.all_asks : [];

    bids.forEach((order) => {
      lookups.push(
        isOwnOrder(order.order_id).then((isOwned) =>
          isOwned ? { ...order, ticker, side: 'BUY' } : null,
        ),
      );
    });

    asks.forEach((order) => {
      lookups.push(
        isOwnOrder(order.order_id).then((isOwned) =>
          isOwned ? { ...order, ticker, side: 'SELL' } : null,
        ),
      );
    });
  }

  const ownedOrders = (await Promise.all(lookups)).filter(Boolean);
  return ownedOrders.sort((left, right) => {
    if (left.ticker !== right.ticker) {
      return left.ticker.localeCompare(right.ticker);
    }
    if (left.side !== right.side) {
      return left.side.localeCompare(right.side);
    }
    return String(left.order_id).localeCompare(String(right.order_id));
  });
}

export function populateOrderBook(container, data) {
  if (!container || !data) {
    return;
  }

  container.classList.add('order-book');
  container.innerHTML = '';
  container.appendChild(buildSideSection('Bids', data.all_bids || []));
  container.appendChild(buildSideSection('Asks', data.all_asks || []));
}
