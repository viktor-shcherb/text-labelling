from __future__ import annotations

import streamlit as st

from label_app.config.settings import get_settings
from label_app.data.models import User
from label_app.services.auth import AuthService
from label_app.ui.components.cookies import get_cookie, put_cookie, remove_cookie


def get_auth_service() -> AuthService:
    if "auth_service" not in st.session_state:
        auth_service = AuthService(
            public_keys=get_settings().public_keys,
            auth_secret=st.secrets.get("AUTH_SECRET"),
            oauth_cfg=st.secrets.get("oauth", {}),
            redirect_uri=st.secrets.get("REDIRECT_URI"),
        )
        st.session_state.auth_service = auth_service

    return st.session_state.auth_service


def sync_cookie_to_session() -> None:
    """If a valid JWT cookie exists, ensure *session_state["user"]* is set."""
    if "user" in st.session_state:
        return

    token = get_cookie("session")
    if not token:
        return

    user = get_auth_service().read_token(token)
    if user:
        st.session_state.user = user


def set_login(user: User) -> None:
    """Persist *user* both in session_state and cookie."""
    st.session_state.user = user

    token = get_auth_service().issue_token(user)
    put_cookie("session", token)


def is_logged_in() -> bool:
    sync_cookie_to_session()
    return st.session_state.get("user") is not None


def sidebar_logout(label: str = "Logout") -> None:
    """Add a small *Logout* button to the sidebar (visible when logged‑in)."""

    sync_cookie_to_session()
    if not st.session_state.get("user"):
        return  # nothing to show

    if st.sidebar.button(label, use_container_width=True):
        remove_cookie("session")
        del st.session_state["user"]
        st.rerun()
