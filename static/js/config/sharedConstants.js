let cachedSharedConstants = null;

export async function getSharedConstants() {
  if (cachedSharedConstants) {
    return cachedSharedConstants;
  }

  const response = await fetch('/app/config/shared_constants.json');
  if (!response.ok) {
    throw new Error(
      `Failed to load /app/config/shared_constants.json (HTTP ${response.status})`,
    );
  }

  cachedSharedConstants = await response.json();
  return cachedSharedConstants;
}

function requireSharedConstant(value, path) {
  if (value === undefined || value === null || value === '') {
    throw new Error(`Missing required shared constant: ${path}`);
  }
  return value;
}

export async function getIdentityHeaderNames() {
  const sharedConstants = await getSharedConstants();

  return {
    user: requireSharedConstant(
      sharedConstants.identity_headers?.user,
      'identity_headers.user',
    ),
    email: requireSharedConstant(
      sharedConstants.identity_headers?.email,
      'identity_headers.email',
    ),
  };
}

export async function getGoogleClientId() {
  const sharedConstants = await getSharedConstants();
  return requireSharedConstant(
    sharedConstants.frontend?.google_client_id,
    'frontend.google_client_id',
  );
}

export async function getClientInfoSocketAddresses() {
  const sharedConstants = await getSharedConstants();

  return {
    primary: requireSharedConstant(
      sharedConstants.frontend?.websocket?.client_info_primary,
      'frontend.websocket.client_info_primary',
    ),
    fallback: requireSharedConstant(
      sharedConstants.frontend?.websocket?.client_info_fallback,
      'frontend.websocket.client_info_fallback',
    ),
  };
}

export async function getOrderbookSocketAddresses() {
  const sharedConstants = await getSharedConstants();

  return {
    primary: requireSharedConstant(
      sharedConstants.frontend?.websocket?.orderbook_primary,
      'frontend.websocket.orderbook_primary',
    ),
    fallback: requireSharedConstant(
      sharedConstants.frontend?.websocket?.orderbook_fallback,
      'frontend.websocket.orderbook_fallback',
    ),
  };
}
