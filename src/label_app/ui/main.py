from pathlib import Path

import streamlit as st

from label_app.ui.components.navigation import setup_navigation


# make expander text the same size as markdown
st.markdown(
    """
    <style>
      /* Only scale the preview label inside the expander’s summary */
      div[data-testid="stExpander"]
        details > summary
        div[data-testid="stMarkdownContainer"] {
        font-size: 1.15em !important;  /* adjust multiplier as needed */
      }
    </style>
    """,
    unsafe_allow_html=True,
)

ICON_PATH = Path(__file__).with_name("static") / "icon.svg"
st.set_page_config(page_title="Text Labelling App", page_icon=str(ICON_PATH), layout="centered")
setup_navigation().run()  # run is called only once
