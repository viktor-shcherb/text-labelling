import streamlit as st


def current_user():
    # 1) Auth0 / social
    if st.user.is_logged_in:
        return st.user
    return None


def is_logged_in():
    return current_user() is not None


def log_out_all():
    st.logout()


def sidebar_logout():
    if not is_logged_in():
        return  # nothing to show

    st.sidebar.button("Log out", use_container_width=True, on_click=log_out_all)
