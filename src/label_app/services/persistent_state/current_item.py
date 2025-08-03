import streamlit as st

from label_app.data.models import Project
from label_app.services.persistent_state.core import session_state_sync, get_authenticated_user

PREFIX = "current_item"


def get_key(project: Project):
    return f"{PREFIX}_{project.slug}_{project.version}"


def get_current_item(project: Project) -> int:
    key = get_key(project)
    session_state_sync(get_authenticated_user(), key)
    return st.session_state.get(key, 0)


def set_current_item(project: Project, current_item: int):
    key = get_key(project)
    st.session_state[key] = current_item
    session_state_sync(get_authenticated_user(), key)
