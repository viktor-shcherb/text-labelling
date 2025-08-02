from __future__ import annotations

import streamlit as st

from label_app.data.models import ChatItem, LabelGroup
from .label_pills import label_pills


def render_chat(
    item: ChatItem,
    labels: list[dict[str, str]],
    *,
    label_groups: dict[str, LabelGroup],
    annotate_roles: list[str],
    key_prefix: str = "msg",
) -> list[dict[str, str]]:
    """Display chat messages with annotation controls.

    Returns the updated ``labels`` list.
    """
    updated = [dict(m) for m in labels]
    for idx, msg in enumerate(item.messages):
        with st.container(border=True):
            st.markdown(f"**{msg.role}**")
            content = msg.content
            if len(content) > 300:
                preview = content[:200] + " … " + content[-100:]
                with st.expander(preview):
                    st.markdown(content)
            else:
                st.markdown(content)

            if msg.role in annotate_roles:
                for lg_name, group in label_groups.items():
                    current = updated[idx].get(lg_name)
                    new_val = label_pills(
                        lg_name,
                        group,
                        current,
                        key=f"{key_prefix}_{idx}_{lg_name}",
                    )
                    if new_val != current:
                        updated[idx][lg_name] = new_val
    return updated
