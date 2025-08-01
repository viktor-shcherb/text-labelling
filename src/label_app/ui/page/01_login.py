import streamlit as st

from label_app.config.settings import get_settings
from label_app.ui.components.auth import get_auth_service, set_login


auth = get_auth_service()

with st.form(key="login_modal", clear_on_submit=False, width="stretch"):
    st.header("Login")
    st.caption("Use one of the methods below to access the app.")

    col1, col2 = st.columns(2)
    with col1:
        if st.form_submit_button("Login with GitHub", use_container_width=True):
            set_login(auth.login_with_oauth("github"))
            st.rerun()
    with col2:
        if st.form_submit_button("Login with Google", use_container_width=True):
            set_login(auth.login_with_oauth("google"))
            st.rerun()

    st.markdown("---")

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
