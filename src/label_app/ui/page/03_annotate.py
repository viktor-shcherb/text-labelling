from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import streamlit as st

from label_app.data.models import Project
from label_app.services.annotations import read_annotations, load_file_annotations
from label_app.services.items import load_items, load_file_items
from label_app.ui.components.annotation_view import render
from label_app.ui.components.auth import current_user, sidebar_logout
from label_app.ui.components.nav_row import nav_row


if "selected_project" not in st.session_state:
    st.switch_page("page/02_project_select.py")

project: Project = st.session_state.selected_project
annot_cls = project.annotation_model()
item_cls = project.item_model()
user = current_user()

items = load_items(project)
if not items:
    st.stop()

project_id = f"{project.slug}-{project.version}"

if "current_item_idx" not in st.session_state:
    st.session_state.current_item_idx = {}
if project_id not in st.session_state.current_item_idx:
    st.session_state.current_item_idx[project_id] = 0

if "new_annotations" not in st.session_state:
    st.session_state.new_annotations = {}
if project_id not in st.session_state.new_annotations:
    st.session_state.new_annotations[project_id] = [None] * len(items)

current_idx = st.session_state.current_item_idx[project_id]
item = items[current_idx]

annotation = st.session_state.new_annotations[project_id][current_idx]
if annotation is None:
    file_items = load_file_items(item_cls, item.key, project.project_root)
    file_annotations = load_file_annotations(annot_cls, user, item.key, project.project_root, file_items)
    annotation = file_annotations[item.idx]

st.header(f"Annotate – {project.name}")

new_annotation = render(project, deepcopy(annotation))
if new_annotation != annotation:
    st.session_state.new_annotations[project_id][current_idx] = new_annotation

#
# if new_labels != labels:
#     st.session_state.labels = new_labels
#     st.session_state.dirty = True
#
#
# def on_save():
#     save_annotation(project, user, item, st.session_state.labels)
#     st.session_state.dirty = False
#
#
# def on_prev():
#     if st.session_state.current_item_idx > 0:
#         st.session_state.current_item_idx -= 1
#         new_item = items[st.session_state.current_item_idx]
#         st.session_state.labels = [dict() for _ in new_item.messages]
#
#
# def on_next():
#     if st.session_state.current_item_idx < len(items) - 1:
#         st.session_state.current_item_idx += 1
#         new_item = items[st.session_state.current_item_idx]
#         st.session_state.labels = [dict() for _ in new_item.messages]
#
# nav_row(on_prev=on_prev, on_save=on_save, on_next=on_next)

sidebar_logout()
img_path = Path(__file__).parent.with_name("static") / "icon_with_border.png"
st.logo(img_path, size="large")

# TODO: cookie sync for annotation persist
