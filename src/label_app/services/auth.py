import hashlib
import hmac
from typing import Literal, Optional

from label_app.data.models import User


class AuthService:
    """Simple authentication helpers."""

    def __init__(self, hashed_keys: dict[str, str]):
        self.hashed_keys = hashed_keys

    def login_with_oauth(self, provider: Literal["github", "google"], code: str | None = None) -> User:
        """Return a dummy user for the OAuth provider."""
        return User(login=f"{provider}_user")

    def login_with_key(self, key: str) -> Optional[User]:
        hashed = hashlib.sha256(key.encode()).hexdigest()
        for stored_hash, login in self.hashed_keys.items():
            if hmac.compare_digest(stored_hash, hashed):
                return User(login=login)
        return None
