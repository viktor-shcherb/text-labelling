import streamlit as st

from label_app.config.settings import get_settings
from label_app.ui.components.auth import get_auth_service, set_login


auth = get_auth_service()

params = st.query_params
provider = params.get("provider")
code = params.get("code")
if provider and code:
    set_login(auth.login_with_oauth(provider, code))
    st.query_params.clear()
    st.rerun()

st.header("Login")
st.caption("Use one of the methods below to access the app.")

col1, col2 = st.columns(2)
with col1:
    st.link_button(
        "Login with GitHub",
        auth.get_authorize_url("github"),
        use_container_width=True,
    )
with col2:
    st.link_button(
        "Login with Google",
        auth.get_authorize_url("google"),
        use_container_width=True,
    )

st.markdown("---")

with st.form(key="key_login", clear_on_submit=False):
    access_key = st.text_input(
        "Access key",
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
