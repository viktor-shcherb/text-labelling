import streamlit as st


def nav_row(*, on_prev=None, on_save=None, on_next=None) -> None:
    """Render Prev/Save/Next buttons with optional callbacks."""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.button("Prev", on_click=on_prev, use_container_width=True)
    with col2:
        st.button(
            "Save",
            on_click=on_save,
            type="primary",
            use_container_width=True,
        )
    with col3:
        st.button("Next", on_click=on_next, use_container_width=True)
