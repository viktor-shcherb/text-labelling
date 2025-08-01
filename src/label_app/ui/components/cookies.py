from __future__ import annotations

from datetime import datetime, timedelta
from streamlit_cookies_controller import CookieController


controller = CookieController(
    key="text-labelling-app",
)


def get_cookie(name: str) -> str | None:
    return controller.get(name)


def put_cookie(
        name: str, value: str,
        *,
        expiry: timedelta | None = None,

) -> None:
    if expiry is None:
        expiry = timedelta(days=7)

    expires_at = datetime.utcnow() + expiry
    return controller.set(
        name, value,
        expires=expires_at,
        secure=True,
        same_site="strict",
    )


def remove_cookie(name: str) -> None:
    return controller.remove(
        name,
        secure=True,
        same_site="strict",
    )
