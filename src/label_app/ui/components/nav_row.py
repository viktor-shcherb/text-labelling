import streamlit as st

def nav_row():
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("Prev")
    with col2:
        st.button("Save")
    with col3:
        st.button("Next")
