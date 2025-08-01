import streamlit as st

from label_app.ui.auth_ui import require_login, sidebar_logout

require_login()

st.header("Project Selection")
st.write("Select a project to start annotating.")

sidebar_logout()
