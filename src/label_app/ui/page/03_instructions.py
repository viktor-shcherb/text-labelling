from pathlib import Path

import streamlit as st

from label_app.services.persistent_state.project import get_project_selection
from label_app.ui.components.auth import sidebar_logout

print("[render] Instructions")

sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

project = get_project_selection()
if project is None:
    raise RuntimeError("Project is not selected!")

st.markdown(
    project.instructions if project.instructions is not None else 'No instructions available for this project'
)
