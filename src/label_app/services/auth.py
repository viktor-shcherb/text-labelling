from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets
from typing import Literal, Optional

from authlib.integrations.requests_client import OAuth2Session
import jwt

from label_app.data.models import User

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRY_DAYS = 7

# OAuth endpoints
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _hash(raw: str) -> str:
    """Return the SHA-256 hex digest of *raw* (UTF-8)."""
    return hashlib.sha256(raw.encode()).hexdigest()


def _safe_equals(a: str, b: str) -> bool:  # pragma: no cover (wrapper)
    """Constant-time equality check to avoid timing attacks."""
    return hmac.compare_digest(a, b)


def _make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) per RFC 7636."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


# add at top
import json, time

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _b64url_decode(s: str) -> bytes:
    # pad to a multiple of 4
    return base64.urlsafe_b64decode(s + "==="[: (4 - len(s) % 4) % 4])



class AuthService:
    """
    OAuth + JWT helper.

    IMPORTANT: instantiate per user session (e.g., per request or in Streamlit's
    st.session_state) so that stored OAuth state/PKCE material isn't shared
    across users.
    """

    def __init__(
        self,
        public_keys: dict[str, str],
        auth_secret: str,
        *,
        oauth_cfg: dict[str, dict[str, str]] | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        if not auth_secret:
            raise ValueError("auth_secret must be provided")

        # normalise the digests to lowercase for reliable comparison
        self._public_keys = {
            login: digest.lower() for login, digest in public_keys.items()
        }
        self._auth_secret = auth_secret
        self._oauth_cfg = oauth_cfg or {}
        self._redirect_uri = redirect_uri

        # per-instance ephemeral storage for state/PKCE (per user session)
        self._oauth_state: dict[str, dict[str, str]] = {}

    # --- Stateless state & PKCE helpers ---
    def _sign(self, msg: bytes) -> str:
        return _b64url(hmac.new(self._auth_secret.encode(), msg, hashlib.sha256).digest())

    def _make_state(self, provider: str) -> str:
        payload = {"p": provider, "iat": int(time.time()), "n": secrets.token_urlsafe(8)}
        body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
        sig = self._sign(body.encode())
        return f"{body}.{sig}"

    def _parse_state(self, state: str, max_age: int = 600) -> dict:
        try:
            body, sig = state.split(".", 1)
        except ValueError:
            raise ValueError("Bad state")
        if self._sign(body.encode()) != sig:
            raise ValueError("Bad state signature")
        data = json.loads(_b64url_decode(body))
        if int(time.time()) - int(data.get("iat", 0)) > max_age:
            raise ValueError("State expired")
        return data

    def _code_verifier_for_state(self, state: str) -> str:
        # 32-byte HMAC → base64url → 43 chars (RFC 7636 requires 43–128)
        return _b64url(hmac.new(self._auth_secret.encode(), state.encode(), hashlib.sha256).digest())

    # ------------------------------------------------------------------
    # OAuth helpers
    # ------------------------------------------------------------------

    def _session(self, provider: Literal["github", "google"]) -> OAuth2Session:
        cfg = self._oauth_cfg.get(provider)
        if not cfg:
            raise ValueError(f"No OAuth config for {provider}")

        return OAuth2Session(
            client_id=cfg["client_id"],
            client_secret=cfg.get("client_secret"),
            redirect_uri=self._redirect_uri,
        )

    def get_authorize_url(self, provider: Literal["github", "google"], *,
                          google_access_type: Literal["online", "offline"] = "online",
                          google_prompt: str = "select_account") -> str:
        session = self._session(provider)
        state = self._make_state(provider)

        if provider == "github":
            url, _ = session.create_authorization_url(
                GITHUB_AUTH_URL,
                scope="read:user",
                state=state,
            )
            return url

        # Google: PKCE using a verifier derived from state (no server storage)
        code_verifier = self._code_verifier_for_state(state)
        code_challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())
        url, _ = session.create_authorization_url(
            GOOGLE_AUTH_URL,
            scope="openid email profile",
            state=state,
            code_challenge=code_challenge,
            code_challenge_method="S256",
            access_type=google_access_type,
            prompt=google_prompt,
            include_granted_scopes="true",
        )
        return url

    def login_with_key(self, key: str) -> Optional[User]:
        """Return a :class:`User` if *key* matches a stored SHA-256 digest."""
        digest = _hash(key)
        for login, stored_digest in self._public_keys.items():
            if _safe_equals(digest, stored_digest):
                return User(login=login)
        return None

    def login_with_oauth(self, code: str, *, state: str) -> User:
        data = self._parse_state(state)  # verifies signature + age
        provider = data["p"]
        session = self._session(provider)

        if provider == "github":
            token = session.fetch_token(
                GITHUB_TOKEN_URL,
                code=code,
                redirect_uri=session.redirect_uri,
                headers={"Accept": "application/json"},
            )
            session.token = token
            resp = session.get(GITHUB_USER_URL)
            resp.raise_for_status()
            login = resp.json()["login"]

        else:  # google
            code_verifier = self._code_verifier_for_state(state)
            token = session.fetch_token(
                GOOGLE_TOKEN_URL,
                code=code,
                redirect_uri=session.redirect_uri,
                code_verifier=code_verifier,
                grant_type="authorization_code",
            )
            session.token = token
            resp = session.get(GOOGLE_USERINFO_URL)
            resp.raise_for_status()
            info = resp.json()
            login = info.get("email")
            if not login:
                raise ValueError("Google profile missing email; check scopes")

        return User(login=login)

    # ------------------------------------------------------------------
    # JWT helpers
    # ------------------------------------------------------------------

    def issue_token(self, user: User, days_valid: int = DEFAULT_EXPIRY_DAYS) -> str:
        """Return a signed JWT for *user* that expires in *days_valid* days."""
        now = dt.datetime.now(dt.timezone.utc)
        exp = now + dt.timedelta(days=days_valid)
        payload = {
            "sub": user.login,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        return jwt.encode(payload, self._auth_secret, algorithm=JWT_ALGORITHM)

    def read_token(self, token: str) -> Optional[User]:
        """Validate *token* and, if valid & not expired, return a :class:`User`."""
        try:
            payload = jwt.decode(
                token,
                self._auth_secret,
                algorithms=[JWT_ALGORITHM],
                options={"require": ["sub", "exp"]},
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
            return None
        return User(login=sub)
