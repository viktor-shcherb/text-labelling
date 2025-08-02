from __future__ import annotations

import streamlit as st

from label_app.data.models import LabelGroup


def label_pills(name: str, group: LabelGroup, current: str | list[str] | None, *, key: str):
    """Render selection widgets for *group* and return the chosen value."""
    if group.single_choice:
        index = group.labels.index(current) if current in group.labels else None
        return st.radio(
            name,
            group.labels,
            index=index,
            horizontal=True,
            key=key,
        )
    else:
        default = current or []
        return st.multiselect(name, group.labels, default=default, key=key)
