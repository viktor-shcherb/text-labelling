import streamlit as st

from label_app.data.models import Project
from label_app.services.persistent_state.core import session_state_sync, get_authenticated_user

KEY = "selected_project"


def get_project_selection() -> Project | None:
    session_state_sync(get_authenticated_user(), KEY)
    result = st.session_state.get(KEY)
    if result is None:
        return None

    return Project.model_validate(result)


def select_project(project: Project):
    project_json = project.model_dump(mode="json")
    st.session_state[KEY] = project_json
    session_state_sync(get_authenticated_user(), KEY)


def is_project_selected() -> bool:
    try:
        session_state_sync(get_authenticated_user(), KEY)
        return st.session_state.get(KEY) is not None
    except RuntimeError:
        return False
