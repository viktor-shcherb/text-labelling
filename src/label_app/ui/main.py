from pathlib import Path

import streamlit as st
from label_app.ui.components.auth import is_logged_in


ICON_PATH = Path(__file__).with_name("static") / "icon.svg"
st.set_page_config(page_title="Text Labelling App", page_icon=str(ICON_PATH), layout="centered")


if is_logged_in():
    VISIBLE_PAGES = [
        st.Page(
            "page/02_project_select.py",
            title="Projects",
            icon=":material/folder_open:",
            default=True
        ),
        st.Page(
            "page/03_annotate.py",
            title="Annotate",
            icon=":material/edit:"
        ),
    ]
    router = st.navigation(VISIBLE_PAGES, position="sidebar", expanded=True)
else:
    VISIBLE_PAGES = [
        st.Page("page/01_login.py", title="Login", default=True),
    ]
    router = st.navigation(VISIBLE_PAGES, position="hidden")

router.run()

