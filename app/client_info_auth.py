import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from models.client import Client

CLIENT_INFO_TOKEN_TTL_SECONDS = int(
    os.environ.get("CLIENT_INFO_WS_TOKEN_TTL_SECONDS", "3600")
)
_CLIENT_INFO_TOKEN_SECRET = os.environ.get("CLIENT_INFO_WS_TOKEN_SECRET")
_CLIENT_INFO_TOKEN_SECRET_BYTES = (
    _CLIENT_INFO_TOKEN_SECRET.encode("utf-8")
    if _CLIENT_INFO_TOKEN_SECRET is not None
    else secrets.token_bytes(32)
)


def _normalize_identity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized else None


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def issue_client_info_token(client: Client) -> str:
    payload = {
        "email": client.email.strip().lower(),
        "username": client.username.strip().lower(),
        "exp": int(time.time()) + CLIENT_INFO_TOKEN_TTL_SECONDS,
    }
    encoded_payload = _urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = _urlsafe_b64encode(
        hmac.new(
            _CLIENT_INFO_TOKEN_SECRET_BYTES,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    return f"{encoded_payload}.{signature}"


def authenticate_client_info_token(email: str, token: str) -> Client | None:
    normalized_email = _normalize_identity(email)
    if normalized_email is None or not token:
        return None

    payload_segment, separator, signature_segment = token.partition(".")
    if not separator or not payload_segment or not signature_segment:
        return None

    expected_signature = _urlsafe_b64encode(
        hmac.new(
            _CLIENT_INFO_TOKEN_SECRET_BYTES,
            payload_segment.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(signature_segment, expected_signature):
        return None

    try:
        payload = json.loads(_urlsafe_b64decode(payload_segment))
    except (ValueError, json.JSONDecodeError):
        return None

    payload_email = _normalize_identity(payload.get("email"))
    payload_username = _normalize_identity(payload.get("username"))
    payload_expiry = payload.get("exp")

    if payload_email != normalized_email or payload_username is None:
        return None
    if not isinstance(payload_expiry, int) or payload_expiry < int(time.time()):
        return None

    client = Client.get_client_by_email(normalized_email)
    if client is None:
        return None
    if payload_username != client.username.strip().lower():
        return None

    return client
