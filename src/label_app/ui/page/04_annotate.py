from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit_hotkeys as hotkeys

from label_app.services.annotations import load_file_annotations, save_annotations
from label_app.services.items import load_items, load_file_items
from label_app.services.persistent_state.current_item import get_current_item, set_current_item
from label_app.services.persistent_state.project import get_project_selection
from label_app.ui.components.annotation_view import render
from label_app.ui.components.auth import current_user, sidebar_logout

print("[render] Annotation")
sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

project = get_project_selection()
if project is None:
    raise RuntimeError("Project is not selected!")

annot_cls = project.annotation_model()
item_cls = project.item_model()
user = current_user()

items = load_items(project)
if not items:
    st.error("No items found!")
    st.stop()


@st.fragment()
def body():
    with st.sidebar:
        hotkeys.activate(
            hotkeys.hk("next", "ArrowRight", help="Next"),
            hotkeys.hk("prev", "ArrowLeft", help="Previous"),
        )

    current_idx = get_current_item(project)
    item = items[current_idx]

    if "cached_annotation" in st.session_state:
        annotation = st.session_state.cached_annotation
    else:
        file_items = load_file_items(item_cls, item.key, project.project_root)
        file_annotations = load_file_annotations(annot_cls, user.email, item.key, project.project_root, file_items)
        annotation = file_annotations[item.idx]
        st.session_state.cached_annotation = annotation

    print(f"[annotate] {annotation.item.key}:{annotation.item.idx}")

    def progress(step: int):
        target_idx = min(len(items) - 1, max(current_idx + step, 0))
        if current_idx == target_idx:
            return

        print(f"[annotate] current idx: {current_idx} -> {target_idx}")

        if "cached_annotation" in st.session_state:
            del st.session_state.cached_annotation
        set_current_item(project, target_idx)
        save_annotations(project, user, [annotation])


    # Page content

    col_header, controls = st.columns([8, 2], vertical_alignment="bottom")
    with col_header:
        st.header(project.name)

    with controls:
        control_prev, control_next = st.columns(2)
        with control_prev:
            st.button(
                "",
                icon=":material/chevron_left:",
                on_click=progress,
                args=(-1,),
                help="Previous",
                disabled=(current_idx == 0),
                key="prev_btn"
            )
            hotkeys.on_pressed("prev", callback=progress, args=(-1,))
        with control_next:
            st.button(
                "",
                icon=":material/chevron_right:",
                on_click=progress,
                args=(1,),
                help="Next",
                disabled=(current_idx == len(items) - 1),
                key="next_btn"
            )
            hotkeys.on_pressed("next", callback=progress, args=(1,))

    def _on_slider_change():
        # slider_idx is 1-based, current_idx is 0-based
        new_idx = st.session_state.slider_idx - 1
        diff = new_idx - current_idx
        if diff != 0:
            progress(diff)

    st.slider(
        f"Annotation progress:",
        min_value=1,
        max_value=len(items),
        value=current_idx + 1,
        key="slider_idx",
        on_change=_on_slider_change,
        help="Jump to annotation by sliding",
    )

    st.session_state.cached_annotation = render(project, annotation)
    save_annotations(project, user, [annotation])


body()

