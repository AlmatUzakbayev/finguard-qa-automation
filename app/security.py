"""Password hashing and JWT access tokens.

Passwords are hashed with PBKDF2-HMAC-SHA256 from the standard library (salted,
600k iterations by default, as recommended by OWASP), so there is no native
dependency to install. The iteration count is stored inside each hash, so changing
the setting later does not break existing passwords.
"""

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings


def hash_password(password: str) -> str:
    iterations = get_settings().password_hash_iterations
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iterations))
    # compare_digest takes the same time for any input: no timing side channel.
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int:
    """Return the user id from a valid token. Raises jwt.InvalidTokenError otherwise
    (bad signature, malformed token, expired token, missing claims)."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
    return int(payload["sub"])
