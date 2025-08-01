from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from typing import Literal, Optional

from authlib.integrations.requests_client import OAuth2Session

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

    def __init__(self, public_keys: dict[str, str], auth_secret: str | None = None, *, oauth_cfg: dict[str, dict[str, str]] | None = None) -> None:
        # normalise the digests to lowercase for reliable comparison
        self._public_keys = {login: digest.lower() for login, digest in public_keys.items()}
        self._auth_secret = auth_secret
        self._oauth_cfg = oauth_cfg or {}

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def _session(self, provider: Literal["github", "google"]) -> OAuth2Session:
        cfg = self._oauth_cfg.get(provider)
        if not cfg:
            raise ValueError(f"No OAuth config for {provider}")

        return OAuth2Session(
            client_id=cfg["client_id"],
            client_secret=cfg["client_secret"],
            redirect_uri=cfg["redirect_uri"],
        )

    def get_authorize_url(self, provider: Literal["github", "google"]) -> str:
        session = self._session(provider)
        if provider == "github":
            url, _ = session.create_authorization_url(
                "https://github.com/login/oauth/authorize",
                scope="read:user",
            )
        else:
            url, _ = session.create_authorization_url(
                "https://accounts.google.com/o/oauth2/v2/auth",
                scope="openid email profile",
                access_type="online",
                prompt="select_account",
            )
        return url

    def login_with_key(self, key: str) -> Optional[User]:
        """Return a :class:`~label_app.data.models.User` if *key* matches."""
        digest = _hash(key)
        for login, stored_digest in self._public_keys.items():
            if _safe_equals(digest, stored_digest):
                return User(login=login)
        return None

    def login_with_oauth(self, provider: Literal["github", "google"], code: str) -> User:
        """Exchange *code* for an access token and return the provider profile."""

        session = self._session(provider)

        if provider == "github":
            token = session.fetch_token(
                "https://github.com/login/oauth/access_token",
                code=code,
                headers={"Accept": "application/json"},
            )
            resp = session.get("https://api.github.com/user", token=token)
            resp.raise_for_status()
            login = resp.json()["login"]
        else:
            token = session.fetch_token(
                "https://oauth2.googleapis.com/token",
                code=code,
            )
            resp = session.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                token=token,
            )
            resp.raise_for_status()
            login = resp.json()["email"]

        return User(login=login)

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

