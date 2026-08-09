"""Auth utilities — password hashing and JWT token handling."""

import hashlib
import hmac
import os
import time
import json
import base64

from fastapi import Header, HTTPException, status

from core.config import settings


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2 + random salt.
    Returns: salt:hash (both hex-encoded, colon-separated)
    """
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored salt:hash string."""
    try:
        salt_hex, key_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


def create_token(user_id: str) -> str:
    """Create a simple JWT-like token (HMAC-signed)."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
        }).encode()
    ).rstrip(b"=").decode()
    signing_input = header + "." + payload
    signature = base64.urlsafe_b64encode(
        hmac.new(
            settings.jwt_secret_key.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
    ).rstrip(b"=").decode()
    return signing_input + "." + signature


def verify_token(token: str) -> str | None:
    """Verify a token and return user_id if valid, None otherwise."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        # Add padding
        header_b64 += "=" * (4 - len(header_b64) % 4) if len(header_b64) % 4 else ""
        payload_b64 += "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""
        sig_b64 += "=" * (4 - len(sig_b64) % 4) if len(sig_b64) % 4 else ""

        signing_input = parts[0] + "." + parts[1]
        expected_sig = base64.urlsafe_b64encode(
            hmac.new(
                settings.jwt_secret_key.encode(),
                signing_input.encode(),
                hashlib.sha256,
            ).digest()
        ).rstrip(b"=").decode()
        if not hmac.compare_digest(sig_b64.rstrip("="), expected_sig):
            return None

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload["sub"]
    except Exception:
        return None


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """Resolve and validate the current user from a Bearer token."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录凭证格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = verify_token(token.strip())
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def require_user_access(requested_user_id: str, current_user_id: str) -> str:
    """Reject attempts to access another user's resources."""
    if not requested_user_id or requested_user_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该用户的数据",
        )
    return current_user_id
