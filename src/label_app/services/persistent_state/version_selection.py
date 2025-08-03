import streamlit as st

from label_app.services.persistent_state.core import session_state_sync, get_authenticated_user

KEY = "version_selection"


def get_version_selection():
    session_state_sync(get_authenticated_user(), KEY)
    return st.session_state.get(KEY)


def set_version_selection(version_selection: dict[str, str]):
    st.session_state[KEY] = version_selection
    session_state_sync(get_authenticated_user(), KEY)


def select_version(slug: str, version: str):
    if KEY not in st.session_state:
        st.session_state[KEY] = {}
    st.session_state[KEY][slug] = version
    session_state_sync(get_authenticated_user(), KEY)
