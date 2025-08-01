from pathlib import Path
import streamlit as st

ICON_PATH = Path(__file__).with_name("static") / "assignment.svg"
st.set_page_config(page_title="Text Label App", page_icon=str(ICON_PATH), layout="wide")

st.write("## Welcome to Text Label App")

st.write("Use the sidebar to navigate between pages.")
