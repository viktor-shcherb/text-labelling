from typing import Literal
import streamlit as st

from label_app.config.settings import get_settings
from label_app.ui.components.auth import get_auth_service, set_login


auth = get_auth_service()


def qp(name, default=None):
    v = st.query_params.get(name, [default])
    return v[0] if isinstance(v, list) else v


# Accept either a plain URL or a (url, state) tuple from the service
def authorize_url(provider: Literal["google", "github"]) -> str:
    out = auth.get_authorize_url(provider)
    if isinstance(out, (tuple, list)):
        return out[0]
    return out


def redirect_now(url: str) -> None:
    # Redirect in-place (no new tab)
    st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)
    st.stop()


# --- Handle OAuth callback ---
code = qp("code")
state = qp("state")
error = qp("error")
error_desc = qp("error_description")

if error:
    st.error(f"OAuth error: {error_desc or error}")

if code and state and not error:
    try:
        # Providerless: service validates 'state' (CSRF) and knows which provider it issued
        user = auth.login_with_oauth(code=code, state=state)
    except Exception as ex:
        st.error(f"Login failed: {ex}")
    else:
        set_login(user)
        st.query_params.clear()
        st.rerun()

login_choice: Literal["github", "google"] | None = None

with st.container(border=True):
    st.header("Login")
    st.caption("Use one of the methods below to access the app.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login with GitHub", use_container_width=True):
            login_choice = "github"
    with col2:
        if st.button("Login with Google", use_container_width=True):
            # disabled=True, help="Login with Google is under renovation"):
            login_choice = "google"

    with st.form(key="key_login", clear_on_submit=False, border=True, enter_to_submit=False):
        access_key = st.text_input(
            "Access key",
            key="access_key_as_password",
            type="password",
            help=f"Ask the administrator for your key: {get_settings().admin_email}",
        )
        if st.form_submit_button("Login with key", use_container_width=True):
            user = auth.login_with_key(access_key)
            if user:
                set_login(user)
                st.rerun()
            else:
                st.error("Invalid key — please try again.")

if login_choice is not None:
    redirect_now(authorize_url(login_choice))
