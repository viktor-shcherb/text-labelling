import base64, hashlib, hmac, datetime as dt
from typing import Optional

import jwt
from label_app.data.models import User


JWT_ALGO = "HS256"
COOKIE_NAME = "key_session"
DEFAULT_DAYS = 7


def _b64url(b: bytes) -> str:   # same helpers you had before
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class KeyAuth:
    """Stateless access-key login (SHA-256 digest + signed JWT cookie)."""

    def __init__(self, *, public_keys: dict[str, str], secret: str):
        self.pub = {u: d.lower() for u, d in public_keys.items()}
        self.sec = secret

    # ---------- login / cookie ----------
    def try_login(self, key: str) -> Optional[User]:
        dig = _hash(key)
        for email, stored in self.pub.items():
            if hmac.compare_digest(dig, stored):
                return User(email=email)
        return None

    def issue_cookie(self, user: User, days: int = DEFAULT_DAYS) -> str:
        now, exp = dt.datetime.utcnow(), dt.timedelta(days=days)
        payload = {
            "sub": user.email,
            "iat": int(now.timestamp()),
            "exp": int((now+exp).timestamp())
        }
        return jwt.encode(payload, self.sec, algorithm=JWT_ALGO)

    def read_cookie(self, token: str) -> Optional[User]:
        try:
            data = jwt.decode(token, self.sec,
                              algorithms=[JWT_ALGO],
                              options={"require": ["sub", "exp"]})
        except jwt.ExpiredSignatureError | jwt.InvalidTokenError:
            return None
        return User(email=data["sub"])
