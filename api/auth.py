"""Telegram Login Widget authentication.

Flow:
1. User clicks Telegram Login Widget on the web page
2. Telegram sends auth data (id, first_name, username, hash, etc.)
3. We verify the hash using the bot token
4. We check if the user exists in our DB and is admin
5. We issue a JWT-like session token
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from bot.config import settings

security = HTTPBearer()

# Secret for signing session tokens (derived from bot token)
_secret_key = hashlib.sha256(settings.bot_token.encode()).hexdigest()


def verify_telegram_auth(auth_data: dict) -> bool:
    """Verify data received from Telegram Login Widget."""
    check_hash = auth_data.pop("hash", None)
    if not check_hash:
        return False

    # Check auth_date is not too old (allow 1 day)
    auth_date = int(auth_data.get("auth_date", 0))
    if time.time() - auth_date > 86400:
        return False

    # Build check string
    data_check_arr = sorted([f"{k}={v}" for k, v in auth_data.items()])
    data_check_string = "\n".join(data_check_arr)

    # Compute hash
    secret = hashlib.sha256(settings.bot_token.encode()).digest()
    computed_hash = hmac.new(
        secret, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return computed_hash == check_hash


def create_session_token(telegram_id: int, role: str) -> str:
    """Create a simple signed session token."""
    payload = {
        "telegram_id": telegram_id,
        "role": role,
        "exp": int(time.time()) + 86400 * 7,  # 7 days
    }
    payload_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        _secret_key.encode(), payload_str.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload_str}|{signature}"


def verify_session_token(token: str) -> dict | None:
    """Verify and decode a session token."""
    try:
        payload_str, signature = token.rsplit("|", 1)
        expected = hmac.new(
            _secret_key.encode(), payload_str.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except (ValueError, json.JSONDecodeError):
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Dependency: extract and verify current user from Authorization header."""
    payload = verify_session_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def is_admin(user: dict) -> bool:
    """Check if user has admin or owner role (case-insensitive)."""
    role = (user.get("role") or "").upper()
    return role in ("ADMIN", "OWNER")


def is_owner(user: dict) -> bool:
    """Check if user has owner (superuser) role."""
    return (user.get("role") or "").upper() == "OWNER"


def require_admin(user: dict):
    """Raise 403 if not admin/owner."""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def require_owner(user: dict):
    """Raise 403 if not owner."""
    if not is_owner(user):
        raise HTTPException(status_code=403, detail="Owner access required")
