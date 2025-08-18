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

# TODO
