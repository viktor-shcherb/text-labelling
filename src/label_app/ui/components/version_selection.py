import json

import streamlit as st

from label_app.ui.components.cookies import get_cookie, put_cookie


def sync_cookie() -> None:
    if "version_selection" in st.session_state:
        selection_json = json.dumps(st.session_state.version_selection)
        put_cookie("version_selection", selection_json)
    else:
        selection_json = get_cookie("version_selection")
        if selection_json is not None:
            st.session_state.version_selection = json.loads(selection_json)


def get_version_selection() -> dict[str, str] | None:
    sync_cookie()
    return st.session_state.get("version_selection")
