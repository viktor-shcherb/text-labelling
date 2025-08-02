import streamlit as st

from label_app.config.settings import get_settings
from label_app.ui.components.auth import set_key_user, key_auth


with st.container(border=True):
    st.header("Login")
    st.caption("Use one of the methods below to access the app.")

    st.button("Log in with Auth0", use_container_width=True, on_click=lambda: st.login("auth0"))

    with st.form(key="key_login", clear_on_submit=False, border=True, enter_to_submit=False):
        access_key = st.text_input(
            "Access key",
            key="access_key_as_password",
            type="password",
            help=f"Ask the administrator for your key: {get_settings().admin_email}",
        )


        def try_login():
            user = key_auth().try_login(access_key)
            if not user:
                st.error("Invalid key.")
            else:
                set_key_user(user)

        if st.form_submit_button("Log in with key", use_container_width=True):
            user = key_auth().try_login(access_key)
            if not user:
                st.error("Invalid key.")
            else:
                set_key_user(user)
                st.rerun()
