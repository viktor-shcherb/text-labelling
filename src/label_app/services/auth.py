from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from typing import Literal, Optional

import jwt

from label_app.data.models import User


JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRY_DAYS = 7


def _hash(raw: str) -> str:
    """Return the SHA-256 hex digest of *raw* (UTF-8)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def _safe_equals(a: str, b: str) -> bool:  # pragma: no cover  (wrapper)
    """Constant-time equality check to avoid timing attacks."""
    return hmac.compare_digest(a, b)


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class AuthService:

    def __init__(self, public_keys: dict[str, str], auth_secret: str | None = None) -> None:
        # normalise the digests to lowercase for reliable comparison
        self._public_keys = {login: digest.lower() for login, digest in public_keys.items()}
        self._auth_secret = auth_secret

    def login_with_key(self, key: str) -> Optional[User]:
        """Return a :class:`~label_app.data.models.User` if *key* matches."""
        digest = _hash(key)
        for login, stored_digest in self._public_keys.items():
            if _safe_equals(digest, stored_digest):
                return User(login=login)
        return None

    def login_with_oauth(self, provider: Literal["github", "google"], code: str | None = None) -> User:
        """Dummy OAuth implementation (to be replaced later).

        """
        # TODO: exchange *code* for an access token & fetch profile from provider
        return User(login=f"{provider}_user")

    def issue_token(self, user: User, days_valid: int = DEFAULT_EXPIRY_DAYS) -> str:
        expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=days_valid)
        payload = {
            "sub": user.login,
            "exp": int(expires_at.timestamp()),
        }
        return jwt.encode(payload, self._auth_secret, algorithm=JWT_ALGORITHM)

    def read_token(self, token: str) -> Optional[User]:
        try:
            payload = jwt.decode(
                token,
                self._auth_secret,
                algorithms=[JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        return User(login=payload["sub"])

