import streamlit as st

from label_app.ui.auth_ui import require_login, sidebar_logout

require_login()

st.header("Annotate")
st.write("Annotation interface coming soon.")

sidebar_logout()
