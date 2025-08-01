import streamlit as st

from label_app.config.settings import settings
from label_app.services.auth import AuthService


def _get_auth_service() -> AuthService:
    if "_auth_service" not in st.session_state:
        st.session_state._auth_service = AuthService(st.secrets.get("keys", {}))
    return st.session_state._auth_service


def require_login() -> None:
    """Display a login modal and block the page until a user is authenticated."""
    if st.session_state.get("user"):
        return

    auth = _get_auth_service()
    with st.modal("Login", key="login_modal"):
        st.header("Login")
        if st.button("Login with Google", use_container_width=True):
            st.session_state.user = auth.login_with_oauth("google")
            st.experimental_rerun()
        if st.button("Login with GitHub", use_container_width=True):
            st.session_state.user = auth.login_with_oauth("github")
            st.experimental_rerun()

        st.divider()
        with st.form("key_login_form"):
            key = st.text_input(
                "Access key",
                type="password",
                help=f"Ask the administrator for your key: {settings.admin_email}",
            )
            if st.form_submit_button("Login with key"):
                user = auth.login_with_key(key)
                if user:
                    st.session_state.user = user
                    st.experimental_rerun()
                else:
                    st.error("Invalid key")

    st.stop()


def sidebar_logout() -> None:
    if st.session_state.get("user"):
        if st.sidebar.button("Logout"):
            for k in list(st.session_state.keys()):
                if k not in {"_auth_service"}:
                    del st.session_state[k]
            st.experimental_rerun()
