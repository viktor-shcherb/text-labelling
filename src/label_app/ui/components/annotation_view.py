from __future__ import annotations

from functools import singledispatch
from typing import TypeVar, overload

import streamlit as st

from label_app.data.models import AnnotationBase, ChatAnnotation, Project, ChatProject, LabelGroup


_AnnotationType = TypeVar("_AnnotationType", bound=AnnotationBase)


@overload
def render(project: ChatProject, annotation: ChatAnnotation) -> ChatAnnotation: ...


@singledispatch
def render(project: Project, annotation: _AnnotationType) -> _AnnotationType:
    raise TypeError(f"No renderer registered for {type(project).__name__}")


def _split_at_nearest_whitespace(s: str, limit: int = 200):
    n = len(s)
    if n == 0:
        return "", ""
    limit = min(limit, max(0, n - 1))  # clamp

    # find whitespace to the left of limit
    left = -1
    for i in range(limit, -1, -1):
        if s[i].isspace():
            left = i
            break

    # find whitespace to the right of limit
    right = -1
    for i in range(limit, n):
        if s[i].isspace():
            right = i
            break

    if left == -1 and right == -1:
        cut = limit
    elif left == -1:
        cut = right
    elif right == -1:
        cut = left
    else:
        cut = left if (limit - left) <= (right - limit) else right

    preview = s[:cut].rstrip() + " ..."
    expanded = "... " + s[cut + 1 :].lstrip()
    return preview, expanded


@render.register
def _render_chat(project: ChatProject, annotation: ChatAnnotation) -> ChatAnnotation:
    """Display chat messages with annotation controls.

    Returns the updated annotation.
    """
    for idx, msg in enumerate(annotation.item.conversation):
        with st.container(border=True):
            st.markdown(f"**{msg.role}**")
            content = msg.content

            if len(content) > 300:
                preview, expanded = _split_at_nearest_whitespace(content, limit=200)
                with st.expander(preview):
                    st.markdown(expanded)
            else:
                st.markdown(content)

            if msg.role in project.chat_options.annotate_roles:
                cols = st.columns([1] * len(project.label_groups), gap="large")

                def handle_label_change(id_, slug):
                    def callback():
                        new_val = st.session_state[f"{id_}_{slug}"]
                        annotation.labels[id_][slug] = new_val if isinstance(new_val, list) else [new_val]

                    return callback

                for (group_slug, group), col in zip(project.label_groups.items(), cols):
                    group: LabelGroup
                    current = annotation.labels[idx].get(group_slug)
                    with col:
                        st.pills(
                            group.title or group_slug, group.labels,
                            selection_mode="single" if group.single_choice else "multi",
                            key=f"{idx}_{group_slug}",
                            on_change=handle_label_change(idx, group_slug),
                            default=current,
                            width="content"
                        )
    return annotation
