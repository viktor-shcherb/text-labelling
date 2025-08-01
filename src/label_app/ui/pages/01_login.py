import streamlit as st

from label_app.ui.auth_ui import require_login, sidebar_logout

require_login()

st.write(f"Logged in as {st.session_state.user.login}")

sidebar_logout()
