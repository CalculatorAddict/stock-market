const DEFAULT_SHARED_CONSTANTS = {
  identity_headers: {
    user: 'X-Actor-User',
    email: 'X-Actor-Email',
  },
  frontend: {
    google_client_id: '933623916878-ipovfk31uqvoidtvj5pcknkod3ggdter.apps.googleusercontent.com',
    websocket: {
      client_info_primary: 'ws://localhost:8000/client_info',
      client_info_fallback: 'ws://mtomecki.pl:8000/client_info',
      orderbook_primary: 'ws://localhost:8000/ws',
      orderbook_fallback: 'ws://mtomecki.pl:8000/ws',
    },
  },
};

let cachedSharedConstants = null;

export async function getSharedConstants() {
  if (cachedSharedConstants) {
    return cachedSharedConstants;
  }

  try {
    const response = await fetch('/app/config/shared_constants.json');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    cachedSharedConstants = await response.json();
  } catch (error) {
    console.warn('Falling back to default shared constants:', error);
    cachedSharedConstants = DEFAULT_SHARED_CONSTANTS;
  }

  return cachedSharedConstants;
}

export async function getIdentityHeaderNames() {
  const sharedConstants = await getSharedConstants();
  const identityHeaders = sharedConstants.identity_headers || {};

  return {
    user: identityHeaders.user || DEFAULT_SHARED_CONSTANTS.identity_headers.user,
    email: identityHeaders.email || DEFAULT_SHARED_CONSTANTS.identity_headers.email,
  };
}

export async function getGoogleClientId() {
  const sharedConstants = await getSharedConstants();
  return (
    sharedConstants.frontend?.google_client_id ||
    DEFAULT_SHARED_CONSTANTS.frontend.google_client_id
  );
}

export async function getClientInfoSocketAddresses() {
  const sharedConstants = await getSharedConstants();
  const websocket = sharedConstants.frontend?.websocket || {};

  return {
    primary:
      websocket.client_info_primary ||
      DEFAULT_SHARED_CONSTANTS.frontend.websocket.client_info_primary,
    fallback:
      websocket.client_info_fallback ||
      DEFAULT_SHARED_CONSTANTS.frontend.websocket.client_info_fallback,
  };
}

export async function getOrderbookSocketAddresses() {
  const sharedConstants = await getSharedConstants();
  const websocket = sharedConstants.frontend?.websocket || {};

  return {
    primary:
      websocket.orderbook_primary ||
      DEFAULT_SHARED_CONSTANTS.frontend.websocket.orderbook_primary,
    fallback:
      websocket.orderbook_fallback ||
      DEFAULT_SHARED_CONSTANTS.frontend.websocket.orderbook_fallback,
  };
}
