from pathlib import Path

import streamlit as st

from label_app.ui.components.navigation import setup_navigation


ICON_PATH = Path(__file__).with_name("static") / "icon.svg"
st.set_page_config(page_title="Text Labelling App", page_icon=str(ICON_PATH), layout="centered")
setup_navigation().run()  # run is called only once
