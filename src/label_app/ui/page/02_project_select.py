import streamlit as st

from label_app.ui.components.auth import sidebar_logout

st.header("Project Selection")
st.write("Select a project to start annotating.")

sidebar_logout()
