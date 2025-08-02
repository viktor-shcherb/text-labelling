import streamlit as st
from label_app.config.settings import get_settings
from label_app.services.key_auth import KeyAuth, COOKIE_NAME
from label_app.ui.components.cookies import put_cookie, get_cookie, remove_cookie


def key_auth() -> KeyAuth:
    if "key_auth" not in st.session_state:
        st.session_state.key_auth = KeyAuth(
            public_keys=get_settings().public_keys,
            secret=st.secrets["AUTH_SECRET"],
        )
    return st.session_state.key_auth


def set_key_user(user):
    st.session_state.key_user = user
    token = key_auth().issue_cookie(user)
    put_cookie(COOKIE_NAME, token)


def _sync_cookie():
    if "key_user" in st.session_state:
        return
    token = get_cookie(COOKIE_NAME)
    if token:
        user = key_auth().read_cookie(token)
        if user:
            st.session_state.key_user = user


def current_user():
    # 1) Auth0 / social
    if st.user.is_logged_in:
        return st.user

    # 2) Access-key
    _sync_cookie()
    return st.session_state.get("key_user")


def is_logged_in():
    return current_user() is not None


def log_out_all():
    # Key-login
    remove_cookie(COOKIE_NAME)
    st.session_state.pop("key_user", None)
    # Social
    st.logout()


def sidebar_logout():
    if not is_logged_in():
        return  # nothing to show

    st.sidebar.button("Log out", use_container_width=True, on_click=log_out_all)
