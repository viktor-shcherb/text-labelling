from pathlib import Path

import streamlit as st

print("[render] Login")

with st.container(border=True):
    st.header("Login")

    st.button("Log in with Auth0", use_container_width=True, on_click=lambda: st.login("auth0"), type="primary")


_, center, _ = st.columns([3, 1, 3])
with center:
    img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
    st.image(img_path, use_container_width=True)
