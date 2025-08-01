from pathlib import Path
import streamlit as st

from label_app.ui.auth_ui import require_login, sidebar_logout

ICON_PATH = Path(__file__).with_name("static") / "icon.svg"
st.set_page_config(page_title="Text Label App", page_icon=str(ICON_PATH), layout="wide")

require_login()

st.write("## Welcome to Text Label App")

st.write("Use the sidebar to navigate between pages.")

sidebar_logout()
