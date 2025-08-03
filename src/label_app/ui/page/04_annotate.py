from __future__ import annotations

from pathlib import Path

import streamlit as st

from label_app.services.annotations import load_file_annotations, save_annotations
from label_app.services.items import load_items, load_file_items
from label_app.services.persistent_state.current_item import get_current_item, set_current_item
from label_app.services.persistent_state.project import get_project_selection
from label_app.ui.components.annotation_view import render
from label_app.ui.components.auth import current_user, sidebar_logout

print("[render] Annotation")

project = get_project_selection()
if project is None:
    raise RuntimeError("Project is not selected!")

annot_cls = project.annotation_model()
item_cls = project.item_model()
user = current_user()

items = load_items(project)
if not items:
    st.stop()

current_idx = get_current_item(project)
item = items[current_idx]

if "cached_annotation" in st.session_state:
    annotation = st.session_state.cached_annotation
else:
    file_items = load_file_items(item_cls, item.key, project.project_root)
    file_annotations = load_file_annotations(annot_cls, user, item.key, project.project_root, file_items)
    annotation = file_annotations[item.idx]
    st.session_state.cached_annotation = annotation


def progress(step: int):
    target_idx = max(len(items), min(current_idx + step, 0))
    if current_idx == target_idx:
        return

    del st.session_state.cached_annotation
    set_current_item(project, target_idx)
    save_annotations(project, user, [annotation])


# Page content

sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

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
            disabled=(current_idx == 0)
        )
    with control_next:
        st.button(
            "",
            icon=":material/chevron_right:",
            on_click=progress,
            args=(1,),
            help="Next",
            disabled=(current_idx == len(items) - 1)
        )

st.progress(current_idx + 1 / len(items), text=f"Annotating {current_idx + 1} out of {len(items)}")

st.session_state.cached_annotation = render(project, annotation)
save_annotations(project, user, [annotation])

