from __future__ import annotations

import streamlit as st

from label_app.data.models import LabelGroup


def label_pills(name: str, group: LabelGroup, current: str | list[str] | None, *, key: str):
    """Render selection widgets for *group* and return the chosen value."""
    return st.pills(
        name, group.labels,
        selection_mode="single" if group.single_choice else "multi",
        default=current,
        key=key,
        width="content"
    )
